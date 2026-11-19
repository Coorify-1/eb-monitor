"""THE ANALYST — daily edition, 06:30 New York.

    python -m analyst.run --out docs/eb-analyst.json            # normal run (skips if not 06:xx NY)
    python -m analyst.run --out docs/eb-analyst.json --force    # run now
    python -m analyst.run --out docs/eb-analyst.json --apply-override   # re-apply analyst/override.json only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

from . import analysis as AN
from . import config as C
from . import sources as S
from . import writer as W
from .sources import log

NY = ZoneInfo("America/New_York")
HERE = pathlib.Path(__file__).parent


# ------------------------------------------------------------------ collect


def collect(today: dt.date):
    A: dict[str, dict] = {}
    raw: dict = {}

    log("Islamic Investment / EB US 100 …")
    isl = S.eb_json(C.ISLAMIC_JSON)
    raw["islamic"] = isl
    eq_series = {"market": None, "shariah": None}
    if isl and (isl.get("index") or {}).get("series"):
        ser = isl["index"]["series"]
        eq_series["shariah"] = [(r[0], r[1]) for r in ser]
        eq_series["market"] = [(r[0], r[2]) for r in ser]

    log("Financial Markets Worker (FRED) …")
    market = {}
    for spec in C.ASSETS:
        if spec[4] == "market":
            market[spec[5]] = S.market_history(spec[5], "3M")

    log("Hard Assets Worker (metals) …")
    mnow = S.metals_now() or {}
    metals = {}
    for spec in C.ASSETS:
        if spec[4] == "metals":
            metals[spec[5]] = S.metals_history(spec[5], "6mo")
            if not metals[spec[5]]:  # fallback: the ~1-month curve published with today's prices
                m = (mnow.get("metals") or {}).get(spec[5]) or {}
                sp = m.get("spark") or []
                if sp:  # one point per business day, ending yesterday
                    days, d = [], today
                    while len(days) < len(sp):
                        d -= dt.timedelta(days=1)
                        if d.weekday() < 5:
                            days.append(d.isoformat())
                    metals[spec[5]] = list(zip(reversed(days), sp))

    log("Currencies (ECB via Frankfurter) …")
    fx = S.fx_history() or {}

    log("Crypto (CoinGecko) …")
    crypto = {}
    for spec in C.ASSETS:
        if spec[4] == "crypto":
            crypto[spec[5]] = S.crypto_history(spec[5]) or S.market_history("CG:" + spec[5].upper(), "3M")
    raw["cryptoGlobal"] = S.crypto_global()

    for spec in C.ASSETS:
        aid, src, sym = spec[0], spec[4], spec[5]
        live = None
        if src == "eq":
            series = eq_series.get(sym)
        elif src == "market":
            series = market.get(sym)
        elif src == "metals":
            series = metals.get(sym)
            m = (mnow.get("metals") or {}).get(sym) or {}
            if S._num(m.get("price")) and S._num(m.get("prev")):
                live = (float(m["price"]), float(m["prev"]))
        elif src == "fx":
            series = fx.get(aid)
        elif src == "crypto":
            series = crypto.get(sym)
        else:
            series = None
        A[aid] = AN.build_asset(spec, series, today, live)
        a = A[aid]
        log(f"  {aid:9s} " + (f"{a['last']:.4g}  d1={a['d1']:+.2f}  z={a['z']:+.2f}{'  STALE' if a['stale'] else ''}"
                               if a["ok"] else "no data"))

    log("Corporate Monitor, Market Outlook, Estate Index, Energy Terminal …")
    raw["monitor"] = S.eb_json(C.MONITOR_JSON)
    raw["outlook"] = S.eb_json(C.OUTLOOK_JSON)
    raw["estate"] = S.estate_world()
    raw["energyNews"] = S.ceii_items("news", 8)
    raw["energyEvents"] = S.ceii_items("events", 12)
    return A, raw


# ------------------------------------------------------------------ page sections (facts + template sentence)


def _say(a):
    if not a.get("ok"):
        return ""
    d = a["d1"] or 0
    lag = AN.lag_note(a.get("asof"))
    if not d:
        return f"{a['name']} was unchanged at {AN.fmt_level(a, a['last'])}{lag}"
    verb = "rose" if d > 0 else "fell"
    return f"{a['name']} {verb} {AN.fmt_move(a, a['d1']).lstrip('+−')} to {AN.fmt_level(a, a['last'])}{lag}"


def sections(A, raw, reg):
    P = lambda k: AN.public(A[k]) if k in A else None  # noqa: E731
    out = {}
    ok = lambda k: A.get(k, {}).get("ok")  # noqa: E731

    # Financial Markets
    f = {"assets": [P(k) for k in ("us_eq", "vix", "us2y", "us10y", "us30y") if ok(k)]}
    if ok("us2y") and ok("us10y"):
        curve = (A["us10y"]["last"] - A["us2y"]["last"]) * 100
        f["curve2s10s"] = f"{AN.sgn(round(curve))}{abs(round(curve))} bp"
    if f["assets"]:
        out["markets"] = {"facts": f, "template": (
            f"{_say(A['us10y']) if ok('us10y') else ''}"
            + (f", leaving the gap over the 2-year at {f['curve2s10s']}" if "curve2s10s" in f else "")
            + f". The {L('markets', 'Financial Markets')} page has yields, commodities and currencies.").lstrip(", ")}

    # Energy
    f = {"assets": [P(k) for k in ("brent", "wti", "natgas") if ok(k)]}
    news = [n["title"] for n in (raw.get("energyNews") or [])[:3]]
    if news:
        f["energyHeadlines"] = news
    if f["assets"]:
        out["energy"] = {"facts": f, "template": "; ".join(_say(A[k]) for k in ("brent", "natgas") if ok(k))
                         + f". Benchmarks, power prices and supply data on the {L('energy', 'Energy Terminal')}."}

    # Crypto & Currencies
    f = {"assets": [P(k) for k in ("btc", "eth", "eurusd", "usdjpy", "gbpusd", "usdchf", "usdcny") if ok(k)]}
    g = raw.get("cryptoGlobal") or {}
    if g.get("mcapChg24h") is not None:
        f["cryptoMarketCap24h"] = AN.fmt_pct(g["mcapChg24h"])
    if f["assets"]:
        out["crypto"] = {"facts": f, "template": "; ".join(_say(A[k]) for k in ("btc", "eurusd") if ok(k))
                         + f". Live rates and a converter on {L('crypto', 'Crypto & Currencies')}."}

    # Hard Assets
    f = {"assets": [P(k) for k in ("gold", "silver", "platinum", "copper") if ok(k)]}
    if ok("gold") and ok("silver") and A["silver"]["last"]:
        f["goldSilverRatio"] = f"{A['gold']['last'] / A['silver']['last']:.1f}"
    if f["assets"]:
        out["metals"] = {"facts": f, "template": "; ".join(_say(A[k]) for k in ("gold", "copper") if ok(k))
                         + f". Precious and base metals on the {L('metals', 'Hard Assets Terminal')}."}

    # Estate Index
    est = raw.get("estate") or []
    if est:
        up = sum(1 for r in est if r["annual"] > 0)
        top = sorted(est, key=lambda r: -r["annual"])[:3]
        bot = sorted(est, key=lambda r: r["annual"])[:3]
        f = {"countries": len(est), "rising": up, "falling": len(est) - up,
             "strongest": [f"{r['name']} {AN.fmt_pct(r['annual'])}" for r in top],
             "weakest": [f"{r['name']} {AN.fmt_pct(r['annual'])}" for r in bot],
             "note": "Yearly house-price change per country, latest official period (slow-moving data)."}
        out["estate"] = {"facts": f, "template": (
            f"House prices are rising in {up} of the {len(est)} countries we track over the past year; "
            f"{top[0]['name']} leads at {AN.fmt_pct(top[0]['annual'])}. Country data on the {L('estate', 'Estate Index')}.")}

    # Corporate Monitor
    mon = raw.get("monitor") or {}
    if mon.get("banking") or mon.get("company"):
        b = (mon.get("banking") or [{}])[0]
        c = (mon.get("company") or [{}])[0]
        f = {"week": mon.get("asOf"), "regime": (mon.get("regime") or {}).get("label"),
             "regimeNote": (mon.get("regime") or {}).get("note"),
             "topBank": f"{b.get('name')} (EB Score {b.get('score')})" if b else None,
             "topCompany": f"{c.get('name')} (EB Score {c.get('score')})" if c else None}
        out["corporate"] = {"facts": f, "template": (
            f"This week's top-ranked bank is {b.get('name')} and the top company is {c.get('name')}, "
            f"under a {str(f['regime']).lower()} backdrop. Rankings on the {L('corporate', 'Corporate Monitor')}.")}

    # Market Outlook
    o = raw.get("outlook") or {}
    if o.get("themes"):
        top = sorted((t for t in o["themes"] if t.get("rank")), key=lambda t: t["rank"])[:5]
        f = {"quarter": o.get("quarter"), "regime": (o.get("regime") or {}).get("label"),
             "regimeNote": (o.get("regime") or {}).get("note"),
             "worldStocks1M": AN.fmt_pct(((o.get("world") or {}).get("perf") or {}).get("m1")),
             "topThemes": [f"{t['name']} ({AN.fmt_pct(t.get('since'))} since the quarter began)" for t in top]}
        out["outlook"] = {"facts": f, "template": (
            f"Our quarterly outlook reads the backdrop as {str(f['regime']).lower()}; {top[0]['name']} leads the five "
            f"themes we follow. Full rankings on the {L('outlook', 'Market Outlook')}.")}

    # Islamic Investment
    isl = raw.get("islamic") or {}
    if ok("shariah"):
        r = (isl.get("index") or {}).get("returns") or {}
        ytd = r.get("YTD") or [None, None]
        f = {"assets": [P("shariah")], "ytdShariah": AN.fmt_pct(ytd[0]), "ytdMarket": AN.fmt_pct(ytd[1]),
             "halalShare": f"{(isl.get('screen') or {}).get('halalShare', 0):.0f}%"}
        out["islamic"] = {"facts": f, "template": (
            f"{_say(A['shariah'])}; it is {f['ytdShariah']} this year against {f['ytdMarket']} for the unscreened market. "
            f"Screens and funds on {L('islamic', 'Islamic Investment')}.")}
    return out


def _short(a):
    return f"{a['name']} {AN.fmt_move(a, a['d1'])}"


VERB_UP = {"metals": "Climbs", "energy": "Rises", "crypto": "Gains", "equities": "Rally", "fx": "Strengthens", "rates": "Climb"}
VERB_DN = {"metals": "Slides", "energy": "Falls", "crypto": "Slips", "equities": "Retreat", "fx": "Weakens", "rates": "Ease"}
SHORT = {"us_eq": "US Stocks", "shariah": "Shariah Stocks", "us2y": "Short-Term Yields", "us10y": "Treasury Yields",
         "us30y": "Long-Term Yields", "brent": "Oil", "wti": "Oil", "natgas": "Gas", "gold": "Gold", "silver": "Silver",
         "platinum": "Platinum", "copper": "Copper", "btc": "Bitcoin", "eth": "Ether", "eurusd": "The Euro",
         "usdjpy": "The Dollar", "gbpusd": "Sterling", "usdchf": "The Dollar", "usdcny": "The Dollar", "vix": "Volatility"}


def _plain(k):
    keep = ("US", "Treasury", "Shariah")
    return " ".join(w if w in keep else w.lower() for w in SHORT.get(k, k).split())


def tone_hint(reg, A, lead=None):
    """'Rising yields and weaker demand prospects added to pressure on silver, which fell more sharply than…'"""
    lead = lead or {}
    ids = [k for k in lead.get("assets", []) if A.get(k, {}).get("ok")]
    if not ids:
        return "Most markets stayed within their usual ranges as investors waited for a clearer signal on rates and growth."
    k = ids[0]
    up = (A[k]["d1"] or 0) >= 0
    forces = []
    if lead.get("type") == "theme":
        forces.append(lead["label"][0].lower() + lead["label"][1:] if not lead["label"][:2].isupper() else lead["label"])
    for mk, s, sup, weigh in DRIVERS.get(A[k]["cls"], []):
        a = A.get(mk)
        if mk == k or not a or not a.get("ok") or a["stale"] or abs(a["z"]) < 0.5:
            continue
        supports = (a["d1"] or 0) * s > 0
        if supports == up:  # the force pushes the same way as the main move
            forces.append(sup if supports else weigh)
    forces = list(dict.fromkeys(forces))[:2] or (["broad selling"] if not up else ["broad buying"])
    name = _plain(k)
    peers = [p for p in PEERS.get(k, []) if A.get(p, {}).get("ok") and _plain(p) != name][:2]
    drv = " and ".join(forces)
    drv = drv[0].upper() + drv[1:]
    if peers and all(abs(A[p]["d1"] or 0) < abs(A[k]["d1"] or 0) for p in peers):
        rel = f", which {'rose' if up else 'fell'} more sharply than {' and '.join(_plain(p) for p in peers)}"
    else:
        rel = ""
    return (f"{drv} {'supported' if up else 'weighed on'} {name}{rel}, though one day's trading is not enough "
            f"to establish the cause.")


SMALL = {"and", "on", "as", "of", "the", "to", "in", "for", "at", "by", "amid", "a", "an", "or"}


def _tc(s: str) -> str:
    """Headline Title Case; short words stay lower case."""
    return " ".join(w if (w.lower() in SMALL) else (w[:1].upper() + w[1:]) for w in s.replace("–", "-").split())


GROUP = {"metals": "Industrial Metals", "energy": "Energy Markets", "crypto": "Digital Assets", "equities": "Stocks",
         "rates": "Bond Markets", "fx": "Currency Markets"}
PEERS = {"silver": ["platinum", "copper", "gold"], "gold": ["silver", "platinum"], "platinum": ["silver", "copper"],
         "copper": ["silver", "platinum"], "brent": ["wti", "natgas"], "wti": ["brent", "natgas"], "btc": ["eth"],
         "eth": ["btc"], "us10y": ["us2y", "us30y"], "us2y": ["us10y"], "us30y": ["us10y"], "us_eq": ["shariah"],
         "eurusd": ["gbpusd", "usdchf"], "usdjpy": ["eurusd"]}
# forces named in the standfirst, by asset class: (market, sign of that market's move that SUPPORTS the asset,
# phrase when it supports, phrase when it weighs)
DRIVERS = {
    "metals": [("us10y", -1, "falling yields", "rising yields"), ("eurusd", 1, "a softer dollar", "a firmer dollar"),
               ("copper", 1, "firmer demand prospects", "weaker demand prospects")],
    "energy": [("eurusd", 1, "a softer dollar", "a firmer dollar"), ("us_eq", 1, "firmer equities", "weaker equities")],
    "crypto": [("us_eq", 1, "firmer equities", "weaker equities"), ("us10y", -1, "falling yields", "rising yields"),
               ("eurusd", 1, "a softer dollar", "a firmer dollar")],
    "equities": [("us10y", -1, "falling yields", "rising yields"), ("brent", -1, "cheaper energy", "higher energy prices"),
                 ("vix", -1, "calmer volatility", "rising volatility")],
    "rates": [("brent", 1, "higher energy prices", "cheaper energy"), ("us_eq", 1, "firmer equities", "weaker equities")],
    "fx": [("us10y", -1, "falling US yields", "rising US yields")],
}


def headline_focus(lead, A):
    ids = [k for k in lead.get("assets", []) if A.get(k, {}).get("ok")]
    if not ids:
        return {}
    k = ids[0]
    group = GROUP.get(A[k]["cls"], "Markets")
    if k == "gold":
        group = "Precious Metals"
    peers = [p for p in PEERS.get(k, []) if A.get(p, {}).get("ok")]
    return {"subject": SHORT.get(k, A[k]["name"]).replace("The ", ""), "group": group,
            "peers": [A[p]["name"] for p in peers[:2]]}


def headline_hint(lead, A):
    """Sentence case, short and factual: 'Platinum leads retreat in metals'."""
    ids = [k for k in lead.get("assets", []) if A.get(k, {}).get("ok")]
    if not ids:
        return "Markets hold within usual ranges"
    k = ids[0]
    up = (A[k]["d1"] or 0) >= 0
    f = headline_focus(lead, A)
    subj = f.get("subject") or A[k]["name"]
    group = f.get("group", "markets").lower().replace("industrial metals", "metals")
    if lead["type"] == "theme":
        return f"{subj} {'rises' if up else 'falls'} amid {lead['label']}"
    day = dt.date.today().toordinal() % 4
    if up:
        opts = [f"{subj} climbs as {group} firm", f"{subj} outpaces {group}", f"{subj} rallies while {group} advance",
                f"Buyers return to {subj.lower() if subj[0].isupper() and subj not in SHORT.values() else subj}"]
    else:
        opts = [f"{subj} slides as {group} weaken", f"{subj} drops further than {group}",
                f"Selling hits {subj}", f"{subj} under pressure in {group}"]
    return opts[day]


def news_list(themes):
    """Every headline found today, one list (titles + links only), newest first, no repeats."""
    out, seen = [], set()
    for t in themes:
        for h in t.get("headlines") or []:
            k = (h.get("title") or "").lower()[:70]
            if not h.get("url") or not k or k in seen:
                continue
            seen.add(k)
            out.append({"theme": t["label"], "title": h["title"], "url": h["url"],
                        "source": h.get("source") or "", "date": h.get("date") or ""})
    return sorted(out, key=lambda x: x["date"], reverse=True)[:30]


def L(k, t):
    return f"[[{k}|{t}]]"


# ------------------------------------------------------------------ edition


def edition_info(now_ny: dt.datetime):
    d = now_ny.date()
    wd = d.weekday()  # Mon=0
    mode = "weekly" if wd == 6 else "weekahead" if wd == 0 else "daily"
    last_close = d - dt.timedelta(days={0: 3, 6: 2}.get(wd, 1))
    return {"date": d.isoformat(), "weekday": d.strftime("%A"), "mode": mode,
            "basedOn": f"{last_close.strftime('%A')}'s close ({last_close.isoformat()})"}


def build(today_ny: dt.datetime):
    ed = edition_info(today_ny)
    AN.SESSION_DATE = re.search(r"\((\d{4}-\d{2}-\d{2})\)", ed["basedOn"]).group(1)
    today = today_ny.date()
    A, raw = collect(today)
    usable = sum(1 for a in A.values() if a.get("ok"))
    if usable < 6:
        raise SystemExit(f"Only {usable} markets answered: not publishing a thin edition.")

    reg = AN.regime(A)
    log(f"Regime: {reg['label']} ({reg['score']})")

    log("Geopolitics and themes (news x markets) …")
    tdoc = json.loads((HERE / "transmission.json").read_text())
    themes = []
    for t in tdoc["themes"]:
        nw = S.theme_news(t, today)
        ev = AN.evaluate_theme(t, nw, A)
        themes.append(ev)
        log(f"  {t['id']:15s} spike={ev['spike']}  {ev['status']}  +{ev['consistent']} -{ev['against']}")
    themes = AN.tidy_themes(themes)
    lead = AN.pick_lead(themes, reg, A)
    log(f"Lead: {lead['type']} · {lead['label']}")

    secs = sections(A, raw, reg)
    name = lambda k: A[k]["name"]  # noqa: E731
    watch_hints = []
    for t in sorted(themes, key=lambda x: -(x["spike"] or 0)):
        if t["status"] == "news_only":
            watch_hints.append(f"{t['label']}: news coverage is up, but markets have not reacted yet.")
    for ev in (raw.get("energyEvents") or [])[:2]:
        watch_hints.append(f"{ev['title']}" + (f" ({ev['date'][:10]})" if ev.get("date") else ""))

    facts = {
        "edition": ed,
        "regime": {"label": reg["label"], "members": [name(k) for k in reg.get("members", [])],
                   "memberIds": reg.get("members", [])},
        "lead": lead,
        "assets": {k: AN.public(a) for k, a in A.items() if a.get("ok")},
        "themes": [{"label": t["label"], "status": t["status"], "direction": t["direction"], "channel": t["channel"],
                    "newsVolume": f"{t['spike']}x normal" if t["spike"] else None,
                    "marketsConsistent": [name(k) for k in t["consistent"]],
                    "marketsAgainst": [name(k) for k in t["against"]],
                    "headlines": [h["title"] for h in t["headlines"]]}
                   for t in themes if t["status"] != "quiet"],
        "sections": {k: v["facts"] for k, v in secs.items()},
        "relationships": [x["text"] for x in AN.relationships(A)],
        "relatedHeadlines": [h["title"] for t in themes for h in (t.get("headlines") or [])[:1]][:6],
        "watchHints": watch_hints[:5],
        "toneHint": tone_hint(reg, A, lead),
        "headlineHint": headline_hint(lead, A),
        "headlineFocus": headline_focus(lead, A),
    }
    # memory of the last editions, so each day reads differently
    arch = pathlib.Path("docs/analyst")
    recent = []
    for pth in sorted(arch.glob("20*.json"), reverse=True)[:6]:
        try:
            old = json.loads(pth.read_text())
            if old.get("edition", {}).get("date") != ed["date"]:
                recent.append({"headline": old["text"]["headline"], "standfirst": old["text"]["tone"],
                               "opening": (old["text"]["lead"] or [""])[0][:160]})
        except Exception:  # noqa: BLE001
            pass
    facts["recentEditions"] = recent[:5]
    # writer facts: drop stale markets so the text never treats an old value as today's
    wf = json.loads(json.dumps(facts))
    wf["assets"] = {k: v for k, v in wf["assets"].items() if not v.get("stale")}
    wf["lead"]["assets"] = [k for k in wf["lead"]["assets"] if k in wf["assets"]]
    wf.pop("headlineHint", None)  # headlineFocus stays: subject and group for the headline  # the AI writes its own headline (story + cause, not numbers)
    wf.pop("toneHint", None)

    text, by = W.write_ai(wf)
    if not text:
        log("Writer: using templates")
        tf = dict(wf)
        tf["sections"] = {k: v for k, v in secs.items()}
        tf["headlineHint"] = facts["headlineHint"]
        tf["toneHint"] = facts["toneHint"]
        text, by = W.write_template(tf), "templates"
        text["briefs"] = {k: v["template"] for k, v in secs.items()}

    # house style: short words in headlines stay lower case (and, on, as, amid…)
    hw = (text.get("headline") or "").split()
    text["headline"] = " ".join(w.lower() if i and w.lower() in SMALL else w for i, w in enumerate(hw))
    now_utc = dt.datetime.now(dt.timezone.utc)
    nxt = (today_ny + dt.timedelta(days=1)).replace(hour=C.PUBLISH_HOUR_NY, minute=C.PUBLISH_MINUTE_NY,
                                                     second=0, microsecond=0)
    return {
        "version": 1,
        "edition": ed,
        "generated": now_utc.isoformat(timespec="seconds"),
        "nextEdition": nxt.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "writtenBy": by,
        "override": False,
        "regime": {k: reg[k] for k in ("id", "label", "score")} | {"members": reg.get("members", [])},
        "lead": lead,
        "text": text,
        "kpis": [AN.public(A[k]) for k in C.KPIS if A.get(k, {}).get("ok")],
        "bars": AN.chart_bars(A),
        "context": AN.chart_context(lead, A),
        "themes": [{k: t[k] for k in ("id", "label", "status", "spike", "direction", "consistent", "against",
                                      "headlines", "newsSource")} for t in themes],
        "markets": {k: AN.public(a) for k, a in A.items()},
        "news": news_list(themes),
        "pages": C.PAGES,
        "sources": ("Economic Bearings pages and engines (Financial Markets, Energy Terminal, Crypto & Currencies, "
                    "Hard Assets, Estate Index, Corporate Monitor, Market Outlook, Islamic Investment). Underlying data: "
                    "FRED, ECB (Frankfurter), CoinGecko, COMEX/NYMEX and LME via EB Metals, CEII, OECD. "
                    "News volume: GDELT. Headlines: Google News; each headline links to the original article."),
        "log": S.LOG[-60:],
    }


# ------------------------------------------------------------------ manual override


def apply_override(doc: dict) -> dict:
    p = HERE / "override.json"
    if not p.exists():
        return doc
    try:
        ov = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        log(f"override.json is not valid JSON ({e}); ignored")
        return doc
    if not ov.get("date") or ov["date"] != doc["edition"]["date"]:
        return doc
    t = dict(doc["text"])
    for k in ("headline", "tone", "lead", "watch"):
        if ov.get(k):
            t[k] = ov[k]
    if isinstance(ov.get("briefs"), dict):
        t["briefs"] = {**t.get("briefs", {}), **{k: v for k, v in ov["briefs"].items() if v}}
    doc["text"] = t
    doc["override"] = True
    log("Manual edits from override.json applied")
    return doc


# ------------------------------------------------------------------ main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/eb-analyst.json")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--apply-override", action="store_true")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    now_ny = dt.datetime.now(NY)

    if a.apply_override:
        if not out.exists():
            print("No edition to edit yet.")
            return
        doc = apply_override(json.loads(out.read_text()))
        write(out, doc)
        return

    force = a.force or os.environ.get("FORCE", "").lower() == "true"
    if not force:
        minutes = now_ny.hour * 60 + now_ny.minute
        start = C.PUBLISH_HOUR_NY * 60 + C.PUBLISH_MINUTE_NY - 5
        if minutes < start:  # before 06:25 New York; later runs still publish if today's edition is missing
            print(f"{now_ny:%H:%M} in New York: outside the publishing window, nothing to do.")
            return
        if out.exists():
            try:
                if json.loads(out.read_text())["edition"]["date"] == now_ny.date().isoformat():
                    print("Today's edition is already published.")
                    return
            except Exception:  # noqa: BLE001
                pass
    doc = apply_override(build(now_ny))
    write(out, doc)


def write(out: pathlib.Path, doc: dict):
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    arch = out.parent / "analyst"
    arch.mkdir(exist_ok=True)
    (arch / f"{doc['edition']['date']}.json").write_text(json.dumps(doc, ensure_ascii=False))
    idx = sorted((p.stem for p in arch.glob("20*.json")), reverse=True)[:120]
    (arch / "index.json").write_text(json.dumps({"editions": idx}))
    print(f"Published {out} · edition {doc['edition']['date']} · written by {doc['writtenBy']}")


if __name__ == "__main__":
    main()
