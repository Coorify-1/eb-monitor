"""THE ANALYST — writing.

The facts (computed by rules) are handed to a free AI model that only writes them up.
Its answer is then checked: every number must come from the facts, every link must be
one of our pages, no advice, no forecasts. If the check fails twice, or no model
answers, the edition is written from sentence templates instead, so a page is always
published.
"""
from __future__ import annotations

import json
import os
import re
import time

import requests

from . import config as C
from .sources import log

LINK_RE = re.compile(r"\[\[([a-z]+)\|([^\]]+)\]\]")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
BANNED = re.compile(
    r"\b(buy|sell|you should|we recommend|recommend(ed)?|guarantee[ds]?|price target|"
    r"will (rise|fall|soar|plunge|crash|rally|drop|climb|surge)|is (set|poised) to|financial advice)\b", re.I)

SECTIONS = ["markets", "energy", "crypto", "metals", "estate", "corporate", "outlook", "islamic"]

SYSTEM = """You are THE ANALYST, the daily market column of Economic Bearings.
Write in clear, calm, editorial English for curious non-specialist readers (Financial Times / The Economist tone).

Hard rules:
1. Use ONLY the facts given. Never add a number, price, date, name or event that is not in the facts.
2. Every number you write must be copied exactly as it appears in the facts (e.g. "+2.4%", "+8 bp", "$63.20"). You may drop a + sign.
3. Causality: say a news theme moved markets ONLY if its status is "confirmed". For "market_only" use cautious words
   ("consistent with", "markets appear to price"). "news_only" themes go in the watch list, never as a cause.
4. No advice, no recommendations, no forecasts of prices. Do not write "will rise/fall".
5. Link to our pages inside the text with this exact syntax: [[key|anchor words]], where key is one of the link keys given.
   Put at least one link in every lead paragraph and in every brief. Never write a URL.
5b. Each market has an asOf date. If it is older than the session named in edition.basedOn (public data such as FRED
   can lag by a day), describe it as "in the latest data" and do not present it as the last session's move.
6. edition.mode: "daily" = analyse the last session (d1Text); "weekly" (Sunday) = review the week (w1Text);
   "weekahead" (Monday) = markets reopen today: recap the last session briefly and focus on what to watch this week.
7. Explain relationships between assets (why oil, yields, gold, the dollar and stocks moved together or apart) in plain words.
8. Be concise. Return ONLY a JSON object with exactly these keys:
{"headline": "<= 95 characters",
 "tone": "one sentence, <= 170 characters, summing up the session",
 "lead": ["3 or 4 short paragraphs, each <= 85 words"],
 "briefs": {"markets": "...", "energy": "...", "crypto": "...", "metals": "...", "estate": "...", "corporate": "...", "outlook": "...", "islamic": "..."},
 "watch": ["exactly 3 items, each <= 28 words"]}
Each brief is one or two sentences (<= 45 words) about that page's market, linking to it."""


# ------------------------------------------------------------------ number check


def _canon(x: float) -> str:
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s or "0"


def allowed_numbers(facts: dict) -> set[str]:
    blob = json.dumps(facts, ensure_ascii=False)
    out = set()
    for t in NUM_RE.findall(blob):
        try:
            v = float(t.replace(",", ""))
        except ValueError:
            continue
        dec = len(t.split(".")[1]) if "." in t else 0
        for k in range(0, dec + 1):
            out.add(_canon(round(v, k)))
    for i in range(0, 13):  # small counts: "three markets", "2 of 5"…
        out.add(str(i))
    return out


def check(out: dict, facts: dict) -> list[str]:
    errs = []
    if not isinstance(out, dict):
        return ["not a JSON object"]
    for k in ("headline", "tone", "lead", "briefs", "watch"):
        if k not in out:
            errs.append(f"missing key {k}")
    if errs:
        return errs
    if not isinstance(out["lead"], list) or not 2 <= len(out["lead"]) <= 4:
        errs.append("lead must be a list of 3 or 4 paragraphs")
    if not isinstance(out["watch"], list) or len(out["watch"]) != 3:
        errs.append("watch must have exactly 3 items")
    if not isinstance(out["briefs"], dict):
        errs.append("briefs must be an object")
        return errs
    texts = [("headline", out["headline"]), ("tone", out["tone"])]
    texts += [(f"lead {i + 1}", p) for i, p in enumerate(out["lead"] or [])]
    texts += [(f"brief {k}", out["briefs"].get(k, "")) for k in SECTIONS if k in facts["sections"]]
    texts += [(f"watch {i + 1}", w) for i, w in enumerate(out["watch"] or [])]
    ok_nums = allowed_numbers(facts)
    for where, t in texts:
        if not isinstance(t, str) or not t.strip():
            errs.append(f"{where} is empty")
            continue
        if "http" in t or "www." in t:
            errs.append(f"{where} contains a URL")
        for key, _ in LINK_RE.findall(t):
            if key not in C.PAGES:
                errs.append(f"{where} links to unknown key '{key}'")
        plain = LINK_RE.sub(lambda m: m.group(2), t)
        if BANNED.search(plain):
            errs.append(f"{where} contains advice or a forecast ('{BANNED.search(plain).group(0)}')")
        for n in NUM_RE.findall(plain):
            try:
                c = _canon(float(n.replace(",", "")))
            except ValueError:
                continue
            if c not in ok_nums:
                errs.append(f"{where}: the number {n} is not in the facts")
    for i, p in enumerate(out["lead"] or []):
        if isinstance(p, str) and not LINK_RE.search(p):
            errs.append(f"lead {i + 1} has no [[key|…]] link")
        if isinstance(p, str) and len(p.split()) > 110:
            errs.append(f"lead {i + 1} is too long")
    for k in SECTIONS:
        b = out["briefs"].get(k)
        if k in facts["sections"] and isinstance(b, str) and not LINK_RE.search(b):
            errs.append(f"brief {k} has no link")
    if isinstance(out["headline"], str) and len(out["headline"]) > 120:
        errs.append("headline too long")
    return errs


# ------------------------------------------------------------------ free AI models


def _call(provider: dict, model: str, messages: list[dict]):
    key = os.environ.get(provider["env"], "").strip()
    if not key:
        return None
    body = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1800,
            "response_format": {"type": "json_object"}}
    for attempt in range(2):
        try:
            r = requests.post(provider["url"], json=body, timeout=120,
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                       "Accept": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
            if r.status_code == 200:
                try:
                    txt = r.json()["choices"][0]["message"]["content"] or ""
                except Exception:  # noqa: BLE001
                    log(f"  writer: {model} answered something unexpected: {r.text[:300]!r}")
                    raise
                txt = re.sub(r"^```(json)?|```$", "", txt.strip()).strip()
                m = re.search(r"\{.*\}", txt, re.S)
                if not m:
                    log(f"  writer: {model} returned no JSON: {txt[:300]!r}")
                    return None
                return json.loads(m.group(0))
            log(f"  writer: {provider['name']} {model} -> HTTP {r.status_code} {r.text[:160]}")
            if r.status_code in (400, 401, 403, 404):
                return None
        except Exception as e:  # noqa: BLE001
            log(f"  writer: {provider['name']} {model} failed: {str(e)[:120]}")
        time.sleep(8)
    return None


def write_ai(facts: dict):
    user = ("Today's facts (JSON). Link keys you may use: "
            + ", ".join(f"{k} = {C.PAGE_NAMES[k]}" for k in C.PAGES)
            + "\n\n" + json.dumps(facts, ensure_ascii=False, indent=1))
    for prov in C.LLM_PROVIDERS:
        for model in prov["models"]:
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
            for attempt in range(2):
                out = _call(prov, model, messages)
                if out is None:
                    break
                errs = check(out, facts)
                if not errs:
                    return out, f"{prov['name']} · {model}"
                log(f"  writer: {model} draft rejected ({len(errs)} issues): " + "; ".join(errs[:6]))
                messages += [{"role": "assistant", "content": json.dumps(out, ensure_ascii=False)},
                             {"role": "user", "content": "Fix these problems and return the full JSON again:\n- "
                              + "\n- ".join(errs[:15])}]
    return None, None


# ------------------------------------------------------------------ templates (always available)


def _L(key, text):
    return f"[[{key}|{text}]]"


def _mv(a: dict) -> str:
    d = a.get("d1")
    if d is None:
        return "was unchanged"
    verb = "rose" if d > 0 else "fell" if d < 0 else "was flat"
    return f"{verb} {a['d1Text'].lstrip('+−')}" if d else verb


def write_template(facts: dict) -> dict:
    A = facts["assets"]
    reg = facts["regime"]
    lead = facts["lead"]
    ok = lambda k: k in A and A[k].get("ok")  # noqa: E731

    def say(k):
        a = A[k]
        return f"{a['name']} {_mv(a)} to {a['lastText']}"

    paras = []
    if lead["type"] == "theme":
        t = next(x for x in facts["themes"] if x["label"] == lead["label"])
        moved = [k for k in lead["assets"] if ok(k)]
        p1 = (f"{t['label']} dominated the session. News coverage of the theme ran at {t['newsVolume']}, "
              f"and markets moved the way this kind of news usually moves them, through {t['channel']}.")
        if moved:
            p1 += " " + "; ".join(say(k) for k in moved[:3]) + "."
        paras.append(p1 + f" Full data on the {_L(A[moved[0]]['page'] if moved else 'markets', C.PAGE_NAMES[A[moved[0]]['page']] if moved else 'Financial Markets')} page.")
    elif lead["type"] == "regime":
        moved = [k for k in reg["memberIds"] if ok(k)]
        paras.append(f"Markets showed a clear {reg['label'].lower()} pattern: " + "; ".join(say(k) for k in moved[:4]) +
                     f". Those moves fit together, which is what gives the pattern its weight. See the "
                     f"{_L('markets', 'Financial Markets dashboard')}.")
    elif lead["type"] == "mover" and ok(lead["assets"][0]):
        k = lead["assets"][0]
        paras.append(f"The largest move of the session relative to its usual range came from {say(k)}. "
                     f"Other markets were calmer, so the move stands largely on its own. Details on the "
                     f"{_L(A[k]['page'], C.PAGE_NAMES[A[k]['page']])} page.")
    else:
        paras.append(f"A quiet session across the markets we follow. Details on the {_L('markets', 'Financial Markets')} page.")

    rates = [k for k in ("us2y", "us10y") if ok(k)]
    if rates:
        paras.append("In bonds, " + " and ".join(f"the {A[k]['name']} moved {A[k]['d1Text']} to {A[k]['lastText']}" for k in rates)
                     + ". Yields move with expectations for inflation and for the Federal Reserve's next steps; "
                     f"the {_L('markets', 'rates table')} has the full curve.")
    hav = [k for k in ("gold", "usdjpy", "eurusd") if ok(k)]
    if hav:
        paras.append("Among havens and currencies, " + "; ".join(say(k) for k in hav)
                     + f". Gold and the yen tend to gain when investors look for safety, and to slip when risk appetite returns. "
                     f"See {_L('metals', 'Hard Assets')} and {_L('crypto', 'Crypto & Currencies')}.")
    if ok("us_eq") or ok("btc"):
        bits = [say(k) for k in ("us_eq", "btc") if ok(k)]
        paras.append("In risk assets, " + "; ".join(bits) + f". The {_L('outlook', 'Market Outlook')} puts the wider trend in context.")
    paras = paras[:4]

    S = facts["sections"]
    briefs = {}
    for key in SECTIONS:
        s = S.get(key)
        if not s:
            continue
        briefs[key] = s.get("template") or ""
    watch = facts.get("watchHints") or []
    watch = (watch + ["How the next session confirms or reverses today's moves.",
                      "Central bank speakers and the next inflation data.",
                      "Energy supply headlines."])[:3]
    head = facts.get("headlineHint") or lead["label"] or "Markets today"
    return {"headline": head[:110], "tone": facts.get("toneHint") or reg["label"],
            "lead": paras, "briefs": briefs, "watch": watch}
