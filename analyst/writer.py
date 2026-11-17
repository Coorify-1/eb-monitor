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
Write clear, calm, editorial English for curious non-specialist readers (Financial Times / The Economist tone).
This is ANALYSIS, not a list of prices: explain WHY markets moved and what it means.

Structure of "lead" (exactly 4 paragraphs):
 1. What happened: the main story of the session in two or three sentences, with the key figures.
 2. Why: the causes. Use "relationships" (cross-asset mechanisms computed from today's moves), the regime,
    the themes and, as concrete examples, the "relatedHeadlines" (paraphrase them, never copy a full headline).
    If the cause is not certain, give the most plausible explanations and say so ("one likely reason…").
 3. Wider impact: how the move spreads to other markets we cover (energy, currencies, crypto, real estate,
    Shariah-compliant shares…), linking to those pages.
 4. Our reading: a short, balanced conclusion: what the moves suggest, what would confirm or contradict it,
    and a question or angle the reader can explore on our pages. No advice, no price forecast.

Hard rules:
1. Use ONLY the facts given. Never add a number, price, date, name or event that is not in the facts.
2. Every number you write must be copied exactly as it appears in the facts (e.g. "+2.4%", "+8 bp", "$63.20").
   After "rose", "fell", "gained" or "lost", drop the + or − sign ("fell 0.6%", never "fell −0.6%").
3. Causality: say a news theme moved markets ONLY if its status is "confirmed". For "market_only" use cautious words
   ("consistent with", "markets appear to price"). Mechanisms in "relationships" may be stated as explanations.
4. No advice, no recommendations, no forecasts of prices. Do not write "will rise/fall".
5. Link to our pages inside the text with this exact syntax: [[key|anchor words]], where key is one of the link keys given.
   Put at least one link in every lead paragraph and in every brief. Never write a URL.
5b. Each market has an asOf date. If it is older than the session named in edition.basedOn (public data such as FRED
   can lag by a day), describe it as "in the latest data" and do not present it as the last session's move.
6. edition.mode: "daily" = analyse the last session (d1Text); "weekly" (Sunday) = review the week (w1Text);
   "weekahead" (Monday) = markets reopen today: recap the last session briefly and focus on what to watch this week.
7. HEADLINE (newspaper style): 6 to 10 words, Title Case, present tense, active verb, NO numbers, no colon.
   Pattern: [what moved] + [verb] + "as"/"on"/"amid" + [the cause]. Example: "Crypto Gains as Regulatory Developments Shape Markets".
   Never a list of prices such as "Bitcoin +2.1%, Ether +3.8%".
8. STANDFIRST ("tone"): one sentence, 14 to 22 words, NO numbers, sentence case, active verbs, concrete nouns.
   Pattern: [main move] + [cause], "while" + [the contrasting move] + [its cause].
   Example: "Digital assets advanced on regulatory optimism, while rising yields weighed on precious and industrial metals."
   Avoid empty phrases such as "markets sent mixed signals" or "the session saw".
Return ONLY a JSON object with exactly these keys:
{"headline": "...",
 "tone": "the standfirst, as in rule 8",
 "lead": ["4 paragraphs as above, each <= 90 words"],
 "briefs": {"markets": "...", "energy": "...", "crypto": "...", "metals": "...", "estate": "...", "corporate": "...", "outlook": "...", "islamic": "..."},
 "watch": ["exactly 3 items, each <= 28 words"]}
Each brief is one or two sentences (<= 45 words): what moved on that page and why it matters, linking to it."""


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
    body = {"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 8000, "reasoning_effort": "low",
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
        lag = f" ({a['lagNote']})" if a.get("lagNote") else ""
        return f"{a['name']} {_mv(a)} to {a['lastText']}{lag}"

    paras = []
    rel = facts.get("relationships") or []
    moved = [k for k in (lead.get("assets") or []) if ok(k)]
    # 1. what happened
    if lead["type"] == "theme":
        t = next(x for x in facts["themes"] if x["label"] == lead["label"])
        p1 = (f"{t['label']} set the tone. " + "; ".join(say(k) for k in moved[:3]) + ".")
    elif lead["type"] == "regime":
        p1 = (f"Markets showed a clear {reg['label'].lower()} pattern. " + "; ".join(say(k) for k in moved[:3]) + ".")
    elif moved:
        p1 = (f"The standout move came from {A[moved[0]]['name'].lower() if A[moved[0]]['class'] == 'metals' else A[moved[0]]['name']}: "
              + "; ".join(say(k) for k in moved[:3]) + ".")
    else:
        p1 = "A quiet session across the markets we follow."
    page0 = A[moved[0]]["page"] if moved else "markets"
    paras.append(p1 + f" The full data is on the {_L(page0, C.PAGE_NAMES[page0])}.")
    # 2. why
    why = ""
    if lead["type"] == "theme":
        t = next(x for x in facts["themes"] if x["label"] == lead["label"])
        why = (f"News coverage of {t['label']} ran at {t['newsVolume']}, and the markets most exposed to it "
               f"moved the way such news usually moves them, through {t['channel']}. ")
        heads = t.get("headlines") or []
        if heads:
            why += f"Among the stories behind it: {heads[0]}. "
    if rel or why:
        paras.append("Why? " + why + " ".join(rel[:2 if why else 3]) + f" The {_L('markets', 'rates and currency tables')} show the moves side by side.")
    else:
        paras.append("No single cause stands out: the moves do not line up with a common driver, and news coverage of "
                     f"the themes we follow was close to normal. See the {_L('markets', 'Financial Markets')} page for the full picture.")
    # 3. wider impact
    imp = [say(k) for k in ("brent", "eurusd", "btc", "us_eq") if ok(k) and k not in moved][:3]
    if imp:
        paras.append("Elsewhere, " + "; ".join(imp) + f". Shariah-screened shares and funds are followed on "
                     f"{_L('islamic', 'Islamic Investment')}, energy on the {_L('energy', 'Energy Terminal')}.")
    # 4. our reading
    if len(moved) >= 2 and rel:
        concl = ("The moves hang together, which makes them more than noise. The test is whether they hold over the "
                 "next sessions or fade.")
    else:
        concl = ("For now this looks like an isolated move rather than a broad shift. Whether it persists, or other "
                 "markets follow, is the question to watch.")
    paras.append("Our reading: " + concl + f" Our {_L('outlook', 'Market Outlook')} puts it in the longer trend.")
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
