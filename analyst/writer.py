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
    r"\b(buy|sell|you should|investors should|readers should|we recommend|recommend(ed)?|guarantee[ds]?|price target|"
    r"will (rise|fall|soar|plunge|crash|rally|drop|climb|surge)|is (set|poised) to|financial advice)\b", re.I)

SECTIONS = ["markets", "energy", "crypto", "metals", "estate", "corporate", "outlook", "islamic"]

SYSTEM = """You are THE ANALYST, the daily market column of Economic Bearings.
Write clear, calm, editorial English for curious non-specialist readers (Financial Times / The Economist tone).
Write each market analysis like an independent financial publication: ANALYSIS, not a list of prices.

"lead" = exactly 4 concise paragraphs, 60 to 85 words each (about 300 words in total):
 1. Market Move: lead with the most significant development of the session. Highlight the main movement and its
    essential contrast. Use only figures that add context (at most 2 figures in this paragraph), never a list of prices.
 2. Key Drivers: explain the developments behind the story. Separate confirmed facts from interpretation:
    state facts plainly, mark interpretation clearly ("a likely reason", "appears to", "is consistent with").
    Never present a correlation as an established cause. Use "relationships" for mechanisms and paraphrase
    "relatedHeadlines" as concrete examples (never copy a full headline). At most 2 figures.
 3. Broader Market Context: connect the main development to relevant moves in interest rates, currencies, equities,
    commodities or other asset classes. Include only meaningful relationships. At most 2 figures.
 4. Outlook: the key developments to watch and what would confirm or change today's reading, without categorical
    predictions. No figures in this paragraph.
Internal links: 3 or 4 in the whole article, placed where they read naturally (descriptive page names, e.g.
"[[metals|Hard Assets Terminal]]"), and at least one in paragraph 4.
Editorial standards: concise paragraphs, no repetition, relevant evidence first, balanced and independent perspective.

Hard rules:
1. Use ONLY the facts given. Never add a number, price, date, name or event that is not in the facts.
2. Every number you write must be copied exactly as it appears in the facts (e.g. "+2.4%", "+8 bp", "$63.20").
   After "rose", "fell", "gained" or "lost", drop the + or − sign ("fell 0.6%", never "fell −0.6%").
3. Causality: say a news theme moved markets ONLY if its status is "confirmed". For "market_only" use cautious words
   ("consistent with", "markets appear to price"). Mechanisms in "relationships" may be stated as explanations.
4. No advice, no recommendations, no forecasts of prices. Do not write "will rise/fall".
5. Link to our pages inside the text with this exact syntax: [[key|anchor words]], where key is one of the link keys given.
   Follow the internal-link rule above for the article; put one link in every brief. Never write a URL.
5b. Each market has an asOf date. If it is older than the session named in edition.basedOn (public data such as FRED
   can lag by a day), describe it as "in the latest data" and do not present it as the last session's move.
6. edition.mode: "daily" = analyse the last session (d1Text); "weekly" (Sunday) = review the week (w1Text);
   "weekahead" (Monday) = markets reopen today: recap the last session briefly and focus on what to watch this week.
7. HEADLINE: 6 to 10 words, no numbers, no colon, present tense, active verb (rise, fall, slump, rally, slide, gain, weigh…).
   Clear hierarchy: start with "headlineFocus.subject" (the main mover), then its movement, then ONE piece of context
   with "as", "on" or "amid" (often the group it belongs to, e.g. "headlineFocus.group"). One angle only, no list of moves.
   Headline Title Case: important words capitalised; and, on, as, of, the, to, in, for, at, by, amid in lower case.
   Good: "Silver Slumps as Industrial Metals Retreat". Good: "Bitcoin and Ether Rise on Regulatory Optimism".
   Bad: "Silver Slumps Amid Pressure Across Industrial Metals" (vague, longer, weaker hierarchy).
8. STANDFIRST ("tone"): one sentence, 15 to 25 words, no numbers, completes the headline without repeating its verb:
   name the forces adding pressure or support (drivers) and the relative performance of the main mover against its peers.
   Factual and sober, nothing beyond the facts; no comma before "as" when it introduces a clause.
   Good: "Rising yields and weaker demand prospects added to pressure on silver, which fell more sharply than platinum and copper."
Return ONLY a JSON object with exactly these keys:
{"headline": "...",
 "tone": "the standfirst, as in rule 8",
 "lead": ["Market Move", "Key Drivers", "Broader Market Context", "Outlook"],
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
    if not isinstance(out["lead"], list) or len(out["lead"]) != 4:
        errs.append("lead must be a list of exactly 4 paragraphs")
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
    paras = [p for p in (out["lead"] or []) if isinstance(p, str)]
    nlinks = sum(len(LINK_RE.findall(p)) for p in paras)
    if not 2 <= nlinks <= 5:
        errs.append(f"the article has {nlinks} internal links; use 3 or 4")
    if len(paras) == 4 and not LINK_RE.search(paras[3]):
        errs.append("paragraph 4 needs one internal link")
    for i, p in enumerate(paras):
        plain = LINK_RE.sub(lambda m: m.group(2), p)
        figs = [n for n in re.findall(r"\d[\d,.]*(?!-(?:year|month|week|day))", plain)]
        limit = 1 if i == 3 else 3
        if len(figs) > limit:
            errs.append(f"lead {i + 1} has {len(figs)} figures; keep only those that add context (max {limit - (0 if i == 3 else 1)})")
        if len(p.split()) > 105:
            errs.append(f"lead {i + 1} is too long (60 to 85 words)")
    for k in SECTIONS:
        b = out["briefs"].get(k)
        if k in facts["sections"] and isinstance(b, str) and not LINK_RE.search(b):
            errs.append(f"brief {k} has no link")
    hl = out["headline"] if isinstance(out["headline"], str) else ""
    n = len(hl.split())
    if not 5 <= n <= 11:
        errs.append(f"headline has {n} words; use 6 to 10")
    if re.search(r"\d", hl) or ":" in hl:
        errs.append("headline must have no numbers and no colon")
    subj = ((facts.get("headlineFocus") or {}).get("subject") or "").lower()
    if subj and subj.split()[0] not in " ".join(hl.lower().split()[:4]):
        errs.append(f"headline must start with the main mover: {facts['headlineFocus']['subject']}")
    sf = out["tone"] if isinstance(out["tone"], str) else ""
    m = len(sf.split())
    if not 13 <= m <= 27:
        errs.append(f"standfirst has {m} words; use 15 to 25")
    if re.search(r"\d", sf):
        errs.append("standfirst must have no numbers")
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
    nm = lambda k: A[k]["name"]  # noqa: E731
    mv = lambda k: f"{'rose' if (A[k]['d1'] or 0) > 0 else 'fell'} {A[k]['d1Text'].lstrip('+−')}"  # noqa: E731
    # 1. Market Move: main movement and its contrast, two figures at most
    if moved:
        k0 = moved[0]
        contra = next((k for k in A if A[k].get("ok") and k not in moved and A[k].get("d1") and A[k].get("z")
                       and (A[k]["d1"] > 0) != ((A[k0]["d1"] or 0) > 0) and abs(A[k]["z"]) >= 1), None)
        p1 = f"{nm(k0)} {mv(k0)}, the most significant move of the session"
        p1 += f" on the {_L(A[k0]['page'], C.PAGE_NAMES[A[k0]['page']])}."
        if contra:
            p1 += f" In contrast, {nm(contra)} {mv(contra)}, a sign that investors did not move in a single direction."
        if len(moved) > 1:
            p1 += f" {nm(moved[1])} moved the same way, which gives the move more weight."
    else:
        p1 = f"Markets stayed broadly within their usual ranges, with no single move standing out. Full data on {_L('markets', 'Financial Markets')}."
    paras.append(p1)
    # 2. Key Drivers: facts first, then marked interpretation
    facts_s, interp = "", ""
    if lead["type"] == "theme":
        t = next(x for x in facts["themes"] if x["label"] == lead["label"])
        facts_s = f"News coverage of {t['label']} rose to {t['newsVolume']}. "
        if t.get("headlines"):
            facts_s += f"Among the reports: {t['headlines'][0]}. "
        interp = f"The pattern of moves is consistent with concerns about {t['channel']}. "
    if rel:
        interp += "A likely reading: " + rel[0][0].lower() + rel[0][1:] + (" " + rel[1] if len(rel) > 1 else "")
    if not (facts_s or interp):
        interp = "No clear driver stands out: the moves do not line up with a common cause, and news coverage of the themes we follow was close to normal."
    paras.append((facts_s + interp).strip())
    # 3. Broader Market Context
    ctx = [k for k in ("us10y", "eurusd", "brent", "btc", "gold", "us_eq") if ok(k) and k not in moved][:2]
    if ctx:
        paras.append("Across asset classes, " + " and ".join(f"{nm(k)} {mv(k)}" for k in ctx)
                     + ". " + (rel[2] if len(rel) > 2 else "These moves show how far the main story spread beyond its own market."))
    else:
        paras.append("Other asset classes moved little, which suggests the main development remained contained.")
    # 4. Outlook
    paras.append("What to watch: whether the main move holds over the next sessions or fades, and whether other markets "
                 "begin to follow. A broader shift would confirm today's reading; a quick reversal would point to a "
                 f"short-lived adjustment. The {_L('outlook', 'Market Outlook')} places it in the longer trend.")
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
