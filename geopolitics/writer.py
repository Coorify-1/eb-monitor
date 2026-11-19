"""GEOPOLITICAL RISK MONITOR — the short view of each risk (two sentences).

The facts are handed to the same free model as THE ANALYST, which only writes them up.
Each view is then checked: no figures, no advice, no forecasts, two sentences at most.
A view that fails the check is written from sentence templates instead, so every risk
always has a view.
"""
from __future__ import annotations

import json
import re

from analyst import config as AC
from analyst.writer import _call
from .sources import log

BANNED = re.compile(
    r"\b(buy|sell|you should|investors should|we recommend|recommend(ed)?|guarantee[ds]?|price target|"
    r"will (rise|fall|soar|plunge|crash|rally|drop|climb|surge|escalate)|is (set|poised) to|financial advice|"
    r"artificial intelligence model|as an ai|language model|aggressor|regime of|martyr|infidel|crusader|zionist entity)\b", re.I)

SYSTEM = """You write the short view of each risk in the Geopolitical Risk Monitor of Economic Bearings.
Tone: calm, precise, editorial English (Financial Times / The Economist), for curious non-specialist readers.
For each risk write EXACTLY two sentences, 22 to 40 words in total:
 1. What is happening: the situation behind the news coverage, using the headlines given (no names of outlets).
 2. What markets are doing about it, in words, using the attention and reaction facts.
Neutrality (house rule): name a conflict by its parties ("the Israel–Hamas war", "the Russia–Ukraine conflict",
"US–Iran tensions"), never by one side's action ("attack on…", "invasion of…" as a title); report actions by all
sides in the same plain, factual verbs; never frame by nationality, religion or ethnicity; no loaded words
("terrorist regime", "aggressor", "martyr").
Hard rules: no digits or numbers at all; no advice; no price forecasts ("will rise/fall"); do not invent events,
people or places that are not in the headlines; mark interpretation ("appears", "is consistent with").
Reading the facts: attention 0 = usual news coverage, 1 = well above usual, 2 or more = exceptional.
reaction +1 = the linked assets move as if the risk were happening, 0 = no sign, −1 = the opposite way.
Return ONLY a JSON object: {"<risk id>": "two sentences", ...} with one entry per risk given."""


ASSET_NAMES = re.compile(
    r"\b(S&P|Nasdaq|FTSE|DAX|CAC|Nikkei|Euro Stoxx|Stoxx|Russell|Hang Seng China|ASX|TOPIX|Treasuries|Treasury|"
    r"U\.S\.|US|UK|German|Japanese)\s?-?\d+(\s?(Y|year)\+?)?\b|\b\d+-year\b|\b\d+Y\+?",
    re.I,
)


def check_view(v) -> list[str]:
    errs = []
    if not isinstance(v, str) or not v.strip():
        return ["empty"]
    # index and asset NAMES may contain digits (S&P 500, Nasdaq 100, U.S. 10-year…): not figures
    if re.search(r"\d", ASSET_NAMES.sub("", v)):
        errs.append("contains a number")
    if BANNED.search(v):
        errs.append("advice or forecast wording")
    n = len(v.split())
    if not 14 <= n <= 48:
        errs.append(f"{n} words (14 to 48 expected)")
    if len(re.findall(r"[.!?](\s|$)", v.strip())) > 3:
        errs.append("more than two sentences")
    if "http" in v or "[[" in v:
        errs.append("contains a link")
    return errs


def _attention_words(a: float) -> str:
    if a >= 1.5:
        return "is drawing exceptional news coverage"
    if a >= 0.6:
        return "is drawing more news coverage than usual"
    if a > -0.4:
        return "is receiving its usual share of news coverage"
    return "has slipped down the news agenda"


def _trend_words(ch: float | None) -> str:
    if ch is None:
        return ""
    if ch >= 0.3:
        return ", and attention rose this week"
    if ch <= -0.3:
        return ", although attention eased this week"
    return ""


def template_view(r: dict) -> str:
    lab = r["label"]
    s1 = f"{lab} {_attention_words(r['attention'])}{_trend_words(r.get('attentionChange'))}."
    x = r["reaction"]
    # an asset named with a figure ("S&P 500", "US 10-year…") is not named: views carry no numbers
    lead = next((a["name"] for a in sorted(r.get("assets") or [], key=lambda a: -a["z"])
                 if (a["move"] > 0) == (a["dir"] > 0) and a["z"] >= 0.5 and not re.search(r"\d", a["name"])), None)
    if x >= 0.4:
        s2 = "Markets are moving as they would if the risk were materialising" + (f", led by {lead}." if lead else ".")
    elif x >= 0.15:
        s2 = "Prices show some signs that investors are pricing the risk, though the moves remain moderate."
    elif x > -0.15:
        s2 = "Prices show little sign that investors are pricing the risk for now."
    else:
        s2 = "The assets most exposed to it are moving the opposite way, suggesting markets see the risk receding."
    return s1 + " " + s2


def write_views(risks: list[dict]) -> dict[str, str]:
    """{risk id: view}. Model first (when a key is set), templates for anything missing."""
    facts = [{"id": r["id"], "risk": r["label"], "attention": r["attention"],
              "attentionChangeThisWeek": r.get("attentionChange"), "reaction": r["reaction"],
              "assets": [{"name": a["name"], "expectedIfRiskHappens": "up" if a["dir"] > 0 else "down",
                          "oneMonthMove": a["text"]} for a in r.get("assets") or []],
              "headlines": [h.get("title", "") for h in r.get("headlines") or []][:4]} for r in risks]
    out: dict[str, str] = {}
    user = "This week's facts (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1)
    for prov in AC.LLM_PROVIDERS:
        for model in prov["models"]:
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
            for attempt in range(2):
                ans = _call(prov, model, messages)
                if not isinstance(ans, dict):
                    break
                bad = {}
                for r in risks:
                    v = ans.get(r["id"])
                    e = check_view(v)
                    if e:
                        bad[r["id"]] = e
                    elif r["id"] not in out:
                        out[r["id"]] = re.sub(r"\s+", " ", v.strip())
                if not bad:
                    return out
                log(f"  views: {model} — {len(bad)} to fix: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in bad.items()))
                messages += [{"role": "assistant", "content": json.dumps(ans, ensure_ascii=False)},
                             {"role": "user", "content": "Fix these views and return the full JSON again:\n- "
                              + "\n- ".join(f"{k}: {', '.join(v)}" for k, v in bad.items())}]
            if len(out) == len(risks):
                return out
    for r in risks:
        out.setdefault(r["id"], template_view(r))
    return out
