"""Weekly EB Monitor run.

python -m engine.run --out docs/eb-monitor.json --cache cache
Needs the GitHub secrets MASSIVE_API_KEY and SEC_CONTACT.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from . import config as C
from . import prices as P
from . import scoring as S
from . import sources as SRC
from . import texts as T
from .fundamentals import extract, shares_outstanding

NY = ZoneInfo("America/New_York")


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- dates

def last_finished_day(now_ny: dt.datetime) -> dt.date:
    """Free price data never includes the current New York day."""
    d = now_ny.date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def next_update(as_of: dt.date, now_ny: dt.datetime) -> dt.datetime:
    """First Monday 7:00 am New York that will publish NEW data: the same rule
    the scheduled run uses to skip ("already published"). A ranking published by
    hand on a Sunday therefore announces the Monday after next, not tomorrow."""
    t = next_monday_7(now_ny)
    for _ in range(2):  # data never runs ahead of the clock; stop after one skipped week
        if last_finished_day(t) > as_of:
            break
        t += dt.timedelta(days=7)
    return t


def next_monday_7(now_ny: dt.datetime) -> dt.datetime:
    d = now_ny.date()
    add = (0 - d.weekday()) % 7
    t = dt.datetime.combine(d + dt.timedelta(days=add), dt.time(7, 0), NY)
    if t <= now_ny:
        t += dt.timedelta(days=7)
    return t


# ---------------------------------------------------------------- country

US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
    "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC PR".split()
)


CA_CODES = {"A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "B0", "Z4"}


def _iso(name):
    try:
        import pycountry
    except ImportError:
        return ""
    name = name.strip().title()
    for cand in [name] + [p.strip() for p in name.split(",")]:
        if not cand:
            continue
        try:
            return pycountry.countries.lookup(cand).alpha_2
        except LookupError:
            pass
        try:
            return pycountry.countries.search_fuzzy(cand)[0].alpha_2
        except LookupError:
            pass
    return ""


def country_from_sec(sub):
    """Country of the head office from SEC addresses ('' if unknown)."""
    for kind in ("business", "mailing"):
        a = ((sub.get("addresses") or {}).get(kind)) or {}
        code = (a.get("stateOrCountry") or "").upper()
        desc = (a.get("stateOrCountryDescription") or "").strip()
        city = (a.get("city") or "").title()
        if code in US_STATES:
            return "US", city
        if code in CA_CODES or "CANADA" in desc.upper():
            return "CA", city
        if desc:
            cc = _iso(desc)
            if cc:
                return cc, city
    inc = (sub.get("stateOfIncorporation") or "").upper()
    city = ((sub.get("addresses") or {}).get("business") or {}).get("city") or ""
    if inc in US_STATES:
        return "US", city.title()
    if inc in CA_CODES:
        return "CA", city.title()
    desc = sub.get("stateOfIncorporationDescription") or ""
    if desc:
        cc = _iso(desc)
        if cc:
            return cc, city.title()
    return "", city.title()


GENERIC = {"bank", "banks", "group", "corp", "corporation", "holdings", "holding", "financial", "inc", "company",
           "limited", "the", "and", "plc", "international", "technologies", "services", "trust"}


def same_company(label, sec_name):
    """Use the Wikidata name only if it clearly names the same company (shares a distinctive word)."""
    import re as _re
    w = lambda x: {t for t in _re.findall(r"[a-z0-9]+", x.lower()) if len(t) >= 3 and t not in GENERIC}
    return bool(label and w(label) & w(sec_name))


# ---------------------------------------------------------------- previous week

def load_prev(path, before=None):
    """Picks of the last published week (before the given data date, so a re-run compares with last week)."""
    j = None
    hist = os.path.join(os.path.dirname(path) or ".", "history")
    if before and os.path.isdir(hist):
        for fn in sorted(os.listdir(hist), reverse=True):
            try:
                h = json.load(open(os.path.join(hist, fn)))
            except Exception:
                continue
            if h.get("asOf", "") < before:
                j = h
                break
    elif not before:
        try:
            j = json.load(open(path))
        except Exception:
            j = None
    if not j or j.get("sample"):
        return {"banking": {}, "company": {}}, None
    return {
        "banking": {i["ticker"]: i["rank"] for i in j.get("banking") or []},
        "company": {i["ticker"]: i["rank"] for i in j.get("company") or []},
    }, j.get("asOf")


# ---------------------------------------------------------------- regime

def regime(wide):
    parts = []

    def last(series, lag=0):
        return series[-1 - lag][1] if len(series) > lag else None

    try:
        curve = SRC.fred("T10Y2Y")
        v = last(curve)
        parts.append(("curve", max(0, min(100, 50 + 40 * v)), "yield curve positive" if v > 0 else "yield curve inverted"))
    except Exception as e:
        log("  regime curve:", e)
    try:
        baa = SRC.fred("BAA10Y")
        v = last(baa)
        s = max(0, min(100, 100 - (v - 1.5) * 40))
        parts.append(("credit", s, "credit spreads calm" if s >= 55 else "credit spreads wide"))
    except Exception as e:
        log("  regime credit:", e)
    try:
        vix = SRC.fred("VIXCLS")
        v = last(vix)
        s = max(0, min(100, 100 - (v - 12) * 4))
        parts.append(("vol", s, "volatility low" if s >= 55 else "volatility high"))
    except Exception as e:
        log("  regime vix:", e)
    try:
        usd = SRC.fred("DTWEXBGS")
        v, v3 = last(usd), last(usd, 63)
        chg = (v / v3 - 1) * 100
        parts.append(("dollar", max(0, min(100, 50 - 10 * chg)), "dollar weakening" if chg < 0 else "dollar strengthening"))
    except Exception as e:
        log("  regime dollar:", e)
    if "SPY" in wide:
        s = wide["SPY"].dropna()
        if len(s) >= 150:
            gap = (s.iloc[-1] / s.iloc[-200:].mean() - 1) * 100
            parts.append(("trend", max(0, min(100, 50 + 5 * gap)), "trend up" if gap > 0 else "trend down"))
    if not parts:
        return None
    sc = float(np.mean([p[1] for p in parts]))
    label = "Risk-on" if sc >= 60 else "Risk-off" if sc <= 40 else "Neutral"
    # explain with the two signals that agree most with the label
    key = sorted(parts, key=lambda p: -abs(p[1] - 50))
    agree = [p for p in key if (p[1] >= 50) == (sc >= 50)][:2] or key[:2]
    note = ", ".join(p[2] for p in agree)
    return {"label": label, "score": round(sc), "note": note[:1].upper() + note[1:]}


# ---------------------------------------------------------------- reader items

def bank_item(r, lead, cur, fx):
    t = r["f"]["t"]
    usd = lambda v: None if v is None or cur not in fx else v / fx[cur]
    ta = usd(t.get("assets"))
    pt = t.get("pretax_income") if t.get("pretax_income") is not None else t.get("net_income")
    metrics = [
        {"label": "Pre-tax profit" if t.get("pretax_income") is not None else "Net profit", "sub": "Latest fiscal year",
         "value": T.money(usd(pt)) if usd(pt) is not None else T.money(pt, cur), "change": _pc(r.get("pretax_chg")), "unit": "%"},
    ]
    if r.get("cet1") is not None:
        metrics.append({"label": "CET1 ratio", "sub": "Core capital strength", "value": T.pct(r["cet1"]),
                        "change": _pt(r["cet1"], r.get("cet1_prev")), "unit": "pt"})
    elif r.get("tang_lev") is not None:
        metrics.append({"label": "Tangible equity / assets", "sub": "Capital cushion", "value": T.pct(r["tang_lev"]),
                        "note": "Shareholders' tangible capital as a share of total assets. Higher means a thicker cushion."})
    if r.get("roe") is not None:
        metrics.append({"label": "Return on equity", "sub": "Profitability", "value": T.pct(r["roe"]),
                        "change": _pt(r["roe"], r.get("roe_prev")), "unit": "pt"})
    if r.get("npl") is not None:
        metrics.append({"label": "Bad loans (NPL)", "sub": "Share of loans", "value": T.pct(r["npl"], 2),
                        "change": _pt(r["npl"], r.get("npl_prev")), "unit": "pt", "good": "down"})
    elif r.get("cost_of_risk") is not None:
        metrics.append({"label": "Cost of risk", "sub": "Provisions / loans", "value": T.pct(r["cost_of_risk"], 2), "good": "down",
                        "note": "New provisions for bad loans as a share of all loans. Lower is better."})
    for lab, k, f in (("Cost / income", "cost_income", T.pct), ("Loans / deposits", "loans_deposits", T.pct),
                      ("Price / tangible book", "ptb", lambda v: T.mult(v, 2).replace("x", ""))):
        if r.get(k) is not None:
            metrics.append({"label": lab, "value": f(r[k])})
    item = _common(r, lead)
    item.update({
        "sector": "Banking",
        "headline": {"label": "Total assets", "value": T.money(ta) if ta else T.money(t.get("assets"), cur),
                     "period": "FY " + (r["f"]["fy_end"] or "")[:4]},
        "metrics": _clean(metrics),
    })
    return item


def company_item(r, lead, cur, fx, as_of):
    t = r["f"]["t"]
    usd = lambda v: None if v is None or cur not in fx else v / fx[cur]
    metrics = [
        {"label": "Revenue", "sub": "Latest fiscal year", "value": T.money(usd(t.get("revenue"))) if usd(t.get("revenue")) is not None else T.money(t.get("revenue"), cur),
         "change": _pc(r.get("revenue_chg")), "unit": "%"},
        {"label": "Operating profit", "sub": "Core business", "value": T.money(usd(r.get("ebit"))) if usd(r.get("ebit")) is not None else T.money(r.get("ebit"), cur),
         "change": _pc(r.get("ebit_chg")), "unit": "%"},
        {"label": "Free cash flow", "sub": "Cash after investment", "value": T.money(usd(r.get("fcf"))) if usd(r.get("fcf")) is not None else T.money(r.get("fcf"), cur),
         "change": _pc(r.get("fcf_chg")), "unit": "%"},
        {"label": "Net debt / EBITDA", "sub": "Debt burden", "value": T.mult(r.get("nd_ebitda")),
         "change": _diff(r.get("nd_ebitda"), r.get("nd_ebitda_prev")), "unit": "pt", "good": "down"},
        {"label": "ROIC", "value": T.pct(r.get("roic"))},
        {"label": "FCF yield", "value": T.pct(r.get("fcf_yield"))},
        {"label": "EV / EBIT", "value": T.mult(r.get("ev_ebit"))},
        {"label": "Piotroski F-score", "value": "—" if r.get("piotroski") is None else f"{r['piotroski']:.0f} / 9",
         "note": "Nine yes/no tests of profit, cash and balance-sheet improvement. 7 or more is strong."},
    ]
    item = _common(r, lead)
    item.update({
        "sector": r["sector"],
        "headline": {"label": "Market value", "value": T.money(r["mcap_usd"]),
                     "period": dt.date.fromisoformat(as_of).strftime("%b %-d")},
        "metrics": _clean(metrics),
    })
    return item


def _pc(v):
    return None if v is None or not math.isfinite(v) else round(v * 100, 1)


def _pt(a, b):
    return None if a is None or b is None else round((a - b) * 100, 1)


def _diff(a, b):
    if a is None or b is None or not math.isfinite(a) or not math.isfinite(b):
        return None
    return round(a - b, 1)


def _clean(ms):
    out = []
    for m in ms:
        if m.get("value") in (None, "—", "n/m%"):
            continue
        out.append({k: v for k, v in m.items() if v is not None})
    return out


OVERRIDES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "overrides.json")


def _overrides():
    try:
        return json.load(open(OVERRIDES_PATH))
    except Exception:
        return {}


def _common(r, lead):
    L = dict(lead or {})
    ov = _overrides().get(r["ticker"]) or {}
    o = ov.get("ceo") or {}
    if o.get("name"):
        if o["name"] != L.get("ceoLabel"):
            for k in ("ceoImg", "photo", "photoCredit", "ceoDesc"):
                L.pop(k, None)  # the Wikidata portrait would show the wrong person
        L["ceoLabel"] = o["name"]
        L["ceoStart"] = str(o.get("since") or "")
    elif o.get("since"):
        L["ceoStart"] = str(o["since"])
    if o:
        if o.get("bio"):
            L["ceoDesc"] = o["bio"].rstrip(".")
    if ov.get("chair"):
        L["chairLabel"] = ov["chair"]
    for k, lk in (("website", "web"), ("employees", "emp"), ("name", "itemLabel")):
        if ov.get(k):
            L[lk] = ov[k]
    if ov.get("country"):
        r = {**r, "country": ov["country"]}
    if ov.get("city"):
        r = {**r, "city": ov["city"]}
    ceo = None
    if L.get("ceoLabel") and not L["ceoLabel"].startswith("Q"):
        ceo = {"name": L["ceoLabel"], "title": "Chief Executive Officer"}
        if L.get("ceoStart"):
            ceo["since"] = L["ceoStart"][:4]
        if L.get("ceoDesc"):
            ceo["bio"] = L["ceoDesc"][:1].upper() + L["ceoDesc"][1:] + "."
        if L.get("photo"):
            ceo["photo"], ceo["photoCredit"] = L["photo"], L["photoCredit"]
    team = []
    if L.get("chairLabel") and not L["chairLabel"].startswith("Q") and (not ceo or L["chairLabel"] != ceo["name"]):
        team.append({"role": "Chair", "name": L["chairLabel"]})
    item = {
        "name": ov.get("name") or (L["itemLabel"] if same_company(L.get("itemLabel"), r["name"]) else T.nice_name(r["name"])),
        "ticker": r["ticker"],
        "exchange": r.get("exchange") or "",
        "country": r["country"] or L.get("cc") or "",
        "city": r.get("city") or (L.get("hqLabel") if L.get("hqLabel") and not L["hqLabel"].startswith("Q") else ""),
        "score": round(float(r["score"])),
        "why": r["why"],
        "risks": r["risks"],
    }
    if L.get("emp"):
        item["employees"] = L["emp"]
    if L.get("logo"):
        item["logo"] = L["logo"]
    if L.get("web"):
        item["website"] = L["web"]
    if ceo and L.get("pressPhoto"):
        ceo["photo"] = L["pressPhoto"]
        ceo["photoCredit"] = o.get("photoCredit") or f"{item['name']}, press kit"
    if ceo:
        item["ceo"] = ceo
    if team:
        item["team"] = team
    return item


# ---------------------------------------------------------------- official logos

def official_logo(ticker, website, out_path):
    folder = os.path.join(os.path.dirname(out_path) or ".", "logos")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9.-]", "_", ticker)
    for ext in ("svg", "png", "jpg", "ico"):
        p = os.path.join(folder, f"{safe}.{ext}")
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < 90 * 86400:
            return f"https://cdn.jsdelivr.net/gh/{REPO}@main/docs/logos/{safe}.{ext}"
    try:
        got = SRC.site_icon(website)
    except Exception as e:
        log("    icon failed", ticker, e)
        got = None
    if not got:
        return None
    data, ext = got
    for old in os.listdir(folder):
        if old.startswith(safe + "."):
            os.remove(os.path.join(folder, old))
    open(os.path.join(folder, f"{safe}.{ext}"), "wb").write(data)
    # jsDelivr serves files from the repository with the right image type (raw GitHub does not for SVG)
    return f"https://cdn.jsdelivr.net/gh/{REPO}@main/docs/logos/{safe}.{ext}"


# ---------------------------------------------------------------- official CEO portraits (press kit)

def official_photo(ticker, url, out_path):
    """Portrait chosen by the editor on the company's press page (data/overrides.json),
    resized and kept in docs/ceo. The file name carries a hash of the source link,
    so a new photo gets a new address and no cache shows the old one."""
    folder = os.path.join(os.path.dirname(out_path) or ".", "ceo")
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9.-]", "_", ticker)
    name = f"{safe}-{hashlib.sha1(url.encode()).hexdigest()[:8]}.jpg"
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        data = SRC.fetch_photo(url)
        if not data:
            log("    press photo could not be downloaded", ticker, url)
            return None
        for old in os.listdir(folder):
            if old.startswith(safe + "-"):
                os.remove(os.path.join(folder, old))
        open(path, "wb").write(data)
    return f"https://cdn.jsdelivr.net/gh/{REPO}@main/docs/ceo/{name}"


# ---------------------------------------------------------------- editorial check page

REPO = os.environ.get("GITHUB_REPOSITORY", "Coorify-1/eb-monitor")


def check_entry(kind, it, r, L, pillars, cur, prev_asof):
    notes = []
    ceo = it.get("ceo") or {}
    src = L.get("ceoSource") or "—"
    if ceo:
        notes.append(f"✅ CEO {ceo['name']} confirmé par : {src}." + (" Date d'entrée confirmée via Wikidata." if ceo.get("since") else ""))
        if L.get("pressPhoto") and ceo.get("photo") == L["pressPhoto"]:
            notes.append(f"📷 Photo officielle de l'espace presse, ajoutée par la rédaction ([source]({L['pressSource']})).")
        elif ceo.get("photo"):
            notes.append(f"📷 Photo libre de Wikimedia Commons ({ceo.get('photoCredit', '')}).")
        else:
            site = str(it.get("website") or "")
            where = (f"dans l'[espace presse]({L['pressPage']})" if L.get("pressPage")
                     else f"dans l'espace presse du [site de l'entreprise]({site if site.startswith('http') else 'https://' + site})" if site
                     else "dans l'espace presse de l'entreprise")
            notes.append(f"📷 Pas de photo libre. Facultatif : prendre la photo officielle du CEO {where} "
                         f"(vérifier que c'est bien {ceo['name']} et que l'usage éditorial est autorisé), "
                         f"puis l'ajouter dans `data/overrides.json`.")
    else:
        notes.append(f"➖ CEO non affiché : {src}.")
    for m in it.get("metrics") or []:
        ch = m.get("change")
        if ch is not None and (abs(ch) > 40 if m.get("unit") == "%" else abs(ch) > 3):
            notes.append(f"ℹ️ {m['label']} : variation de {ch:+.1f}{' pt' if m.get('unit') == 'pt' else '%'}, chiffre tel que déposé à la SEC.")
    missing = [lab for k, lab, _ in pillars if not any(p["key"] == k for p in it.get("pillars") or [])]
    if missing:
        notes.append("ℹ️ Pilier(s) sans données publiées : " + ", ".join(missing) + " ; le score utilise les autres piliers.")
    sec = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={r['cik']}&type={'' if r.get('foreign') else '10-K'}&dateb=&owner=include&count=10"
    return {"kind": kind, "it": it, "notes": notes, "sec": sec, "fy": r["f"]["fy_end"]}


def write_check(path, out, checks, reg):
    L = [
        f"# Contrôle automatique — semaine {out['week']} (données au {out['asOf']})",
        "",
        f"Généré le {out['generated'][:16].replace('T', ' ')} UTC. Aucune action manuelle n'est nécessaire : "
        "toute information qui n'est pas confirmée par un document officiel est masquée automatiquement.",
        "",
    ]
    if reg:
        L += [f"**EB Market Regime :** {reg['label']} {reg['score']}/100 — {reg['note']}", ""]
    for kind, title in (("banking", "Banking Monitor"), ("company", "Company Monitor")):
        L += [f"## {title}", ""]
        for c in [c for c in checks if c["kind"] == kind]:
            it = c["it"]
            move = "" if "prevRank" not in it else (" · nouveau" if it["prevRank"] is None else f" · semaine passée : n°{it['prevRank']}")
            L += [
                f"### {it['rank']}. {it['name']} ({it['ticker']}) — score {it['score']}/100{move}",
                "",
                f"- {it['headline']['label']} : {it['headline']['value']} · exercice clos le {c['fy']} · [dépôts SEC]({c['sec']})",
                "- Chiffres clés : " + " · ".join(
                    f"{m['label']} {m['value']}" + (f" ({m['change']:+.1f}{' pt' if m.get('unit') == 'pt' else '%'})" if m.get("change") is not None else "")
                    for m in (it.get("metrics") or [])[:4]
                ),
            ] + [f"- {n}" for n in c["notes"]] + [""]
    L += ["---", "", "*Sources : dépôts officiels à la SEC (comptes XBRL, rapports annuels 10-K / 20-F / 40-F, déclarations Form 4), "
          "Wikidata pour les compléments (photo libre, date d'entrée) uniquement quand ils concordent avec la SEC.*", ""]
    open(path, "w").write("\n".join(L))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/eb-monitor.json")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    now = dt.datetime.now(NY)
    day = last_finished_day(now)
    _, published = load_prev(a.out)
    force = a.force or os.environ.get("FORCE") == "true"
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and not force:
        if now.hour < 7:
            log("Before 7:00 am New York: waiting for the next scheduled run.")
            return
        if published and published >= day.isoformat():
            log("This week's ranking is already published.")
            return

    massive, sec = SRC.Massive(), SRC.SEC()

    log("1/7 Prices")
    df = P.update(a.cache, massive, day, log=log)
    wide, vol = P.series_by_ticker(df)
    mom = P.momentum_table(wide, vol)
    as_of = str(mom["date"].max())
    log(f"  {len(mom)} tickers, data as of {as_of}")
    prev, prev_asof = load_prev(a.out, before=as_of)
    log(f"  compared with the week of {prev_asof}" if prev_asof else "  first published week")

    log("2/7 Universe")
    tick = pd.DataFrame(sec.tickers())
    tick = tick[tick["exchange"].isin(["NYSE", "Nasdaq"])]
    tick = tick.rename(columns={"cik": "cik"}).dropna(subset=["ticker"])
    tick["ticker_m"] = tick["ticker"].str.replace("-", ".", regex=False)
    u = tick.merge(mom, left_on="ticker_m", right_index=True)
    u = u.sort_values("adv", ascending=False).drop_duplicates("cik")
    keep = set(prev["banking"]) | set(prev["company"])
    cand = pd.concat([u.head(C.CANDIDATES), u[u["ticker"].isin(keep)]]).drop_duplicates("cik")
    log(f"  {len(cand)} candidates")

    log("3/7 Company filings (SEC)")
    det_path = os.path.join(a.cache, "details.json")
    details = json.load(open(det_path)) if os.path.exists(det_path) else {}
    det_budget = 150  # market values of foreign listings, refreshed every 90 days
    recs, diags = [], []
    for i, c in enumerate(cand.itertuples()):
        if (i + 1) % 100 == 0:
            log(f"    {i + 1}/{len(cand)}")
        sub = sec.submissions(c.cik)
        if not sub:
            continue
        try:
            sic = int(sub.get("sic") or 0)
        except ValueError:
            sic = 0
        if not sic or sic == 6770:  # 6770 = blank-check shells
            continue
        forms = set((sub.get("filings") or {}).get("recent", {}).get("form", [])[:200])
        foreign = bool(forms & {"20-F", "40-F", "6-K"})
        facts = sec.facts(c.cik)
        if not facts:
            continue
        f = extract(facts)
        diag = {"ticker": c.ticker, "sic": sic, "foreign": foreign, "fy_end": f["fy_end"], "cur": f["currency"]}
        diags.append(diag)
        if not f["fy_end"] or f["fy_end"] < (now.date() - dt.timedelta(days=560)).isoformat():
            diag["drop"] = "old or no annual data"
            continue
        t = f["t"]
        dep = t.get("deposits")
        is_bank = sic in C.BANK_SIC or (
            C.is_financial(sic) and dep and t.get("loans") and t.get("assets") and dep / t["assets"] > 0.3
        )
        if C.is_financial(sic) and not is_bank:
            diag["drop"] = "financial, not a bank"
            continue
        diag["bank"] = bool(is_bank)
        country, city = country_from_sec(sub)
        sh = None if foreign else shares_outstanding(facts)
        mcap = sh * c.close if sh else None
        if mcap is None:
            d = details.get(c.ticker)
            stale = not d or d.get("at", "") < (now.date() - dt.timedelta(days=90)).isoformat()
            if stale and det_budget > 0:
                try:
                    x = massive.details(c.ticker_m)
                    if x.get("market_cap"):
                        d = {"mc": x["market_cap"], "close": c.close, "at": now.date().isoformat()}
                        details[c.ticker] = d
                except Exception as e:
                    log("    details failed", c.ticker, e)
                det_budget -= 1
            if d and d.get("mc"):
                mcap = d["mc"] * c.close / d["close"]
        diag["mcap_bn"] = None if not mcap else round(mcap / 1e9, 1)
        diag["country"] = country
        diag["missing"] = [k for k in ("revenue", "operating_income", "cfo", "equity", "net_income", "loans", "deposits", "cet1_ratio") if k not in t]
        rec_sub = {"filings": {"recent": {k: v[:400] for k, v in ((sub.get("filings") or {}).get("recent") or {}).items()
                                          if k in ("form", "accessionNumber", "primaryDocument", "filingDate")}}}
        recs.append({"sub": rec_sub, "website": sub.get("website") or "", "bank": bool(is_bank),
            "ticker": c.ticker, "cik": int(c.cik), "name": c.name, "exchange": c.exchange, "sic": sic,
            "sector": "Banks" if is_bank else C.sector_of(sic), "country": country or "", "city": city, "foreign": foreign,
            "close": c.close, "mcap_usd": mcap, "f": f,
            "mom": {k: getattr(c, k, None) for k in ("mom_12_1", "trend_200", "ret_12m")},
        })
    json.dump(details, open(det_path, "w"))
    json.dump(diags, open(os.path.join(a.cache, "diagnostics.json"), "w"), indent=0)
    log(f"  {len(recs)} companies with filings")

    log("4/7 Scores")
    fx = SRC.fx_per_usd()
    rows = []
    for r in recs:
        if not r["mcap_usd"] or r["mcap_usd"] < C.MIN_MARKET_CAP_USD:
            continue
        cur = r["f"]["currency"] or "USD"
        if cur not in fx:
            continue  # cannot compare values without an exchange rate
        r["mcap_local"] = r["mcap_usd"] * fx[cur]
        r["kind"] = "banking" if r["bank"] else "company"
        m = S.bank_metrics(r) if r["kind"] == "banking" else S.company_metrics(r)
        rows.append({**{k: r[k] for k in ("ticker", "kind", "sector", "country", "mcap_usd")}, **m, "_r": r})
    data = pd.DataFrame(rows)
    banks = data[data.kind == "banking"].copy()
    comps = data[data.kind == "company"].copy()
    log(f"  eligible: {len(banks)} banks, {len(comps)} companies (market value > $10bn)")
    for name, d, parts in (("banks", banks, S.BANK_PARTS), ("companies", comps, S.COMPANY_PARTS)):
        cov = {m: f"{d[m].notna().mean() * 100:.0f}%" for items in parts.values() for m, _, _ in items if m in d}
        log(f"  data coverage {name}: {cov}")
    banks = S.score(banks, S.BANK_PARTS, C.BANK_PILLARS)
    comps = S.score(comps, S.COMPANY_PARTS, C.COMPANY_PILLARS, group_col="sector")
    pb = S.pick(banks, prev["banking"], sector_cap=False)
    pc = S.pick(comps, prev["company"], sector_cap=True)
    log("  banks:", ", ".join(f"{r.ticker} {r.score:.0f}" for r in pb.itertuples()))
    log("  companies:", ", ".join(f"{r.ticker} {r.score:.0f}" for r in pc.itertuples()))

    log("5/7 Leadership (Wikidata, Wikimedia Commons)")
    picks = pb.to_dict("records") + pc.to_dict("records")
    lead = SRC.wikidata_leadership([p["_r"]["cik"] for p in picks])
    # companies Wikidata does not link to their SEC number: find them by their New York ticker
    missing = [p["_r"] for p in picks if not same_company((lead.get(p["_r"]["cik"]) or {}).get("itemLabel"), p["_r"]["name"])]
    if missing:
        by_t = SRC.wikidata_leadership([r["ticker"] for r in missing], by_ticker=True)
        for r in missing:
            d = by_t.get(r["ticker"])
            if d and same_company(d.get("itemLabel"), r["name"]):
                lead[r["cik"]] = d
    # every leader shown must be confirmed by an official SEC document
    cutoff = (now.date() - dt.timedelta(days=3 * 365)).isoformat()
    for p in picks:
        r = p["_r"]
        L = lead.setdefault(r["cik"], {})
        try:
            text, doc = SRC.annual_report_text(sec, r["cik"], r["sub"], deep=r["foreign"])
            name, src, wd_ok = SRC.verified_ceo(sec, r["cik"], r["sub"], r["foreign"], L.get("ceoLabel"), text, doc)
        except Exception as e:
            log("    leadership check failed", r["ticker"], e)
            text, name, src, wd_ok = "", None, "check failed", False
        if not wd_ok:
            for k in ("ceoImg", "photo", "photoCredit", "ceoDesc", "ceoStart"):
                L.pop(k, None)
        if name:
            L["ceoLabel"] = name
        else:
            L.pop("ceoLabel", None)
        L["ceoSource"] = src
        if L.get("chairLabel") and not SRC.named_near(text, L["chairLabel"], "Chair"):
            L.pop("chairLabel")
        if L.get("emp") and (L.get("empDate") or "") < cutoff:
            L.pop("emp")  # staff numbers older than three years are not shown
        if L.get("ceoImg"):
            ph = SRC.commons_photo(L["ceoImg"])
            if ph:
                L.update(ph)
        if name and not L.get("photo"):
            words = [w for w in re.findall(r"[A-Za-z]+", r["name"]) if w.lower() not in GENERIC]
            ph = SRC.person_photo(name, L.get("qid") if same_company(L.get("itemLabel"), r["name"]) else None, words)
            if ph:
                L["photo"], L["photoCredit"] = ph["photo"], ph["photoCredit"]
                if ph.get("desc") and not L.get("ceoDesc"):
                    L["ceoDesc"] = ph["desc"]
        oc = (_overrides().get(r["ticker"]) or {}).get("ceo") or {}
        if oc.get("photo"):
            L["pressPhoto"] = official_photo(r["ticker"], oc["photo"], a.out)
            L["pressSource"] = oc.get("photoSource") or oc["photo"]
        if (name or oc.get("name")) and not L.get("photo") and not L.get("pressPhoto"):
            try:
                L["pressPage"] = SRC.press_page(L.get("web") or r.get("website"))
            except Exception as e:
                log("    press page search failed", r["ticker"], e)
        if L.get("logoFile") and same_company(L.get("itemLabel"), r["name"]):
            L["logo"] = SRC.commons_logo(L["logoFile"])
        if not L.get("logo"):
            # the icon the company publishes on its own website, kept in docs/logos
            site = L.get("web") or r.get("website")
            L["logo"] = official_logo(r["ticker"], site, a.out)
        log(f"    {r['ticker']}: CEO {name or '—'} ({src}){' + photo' if L.get('photo') else ''}{' + press photo' if L.get('pressPhoto') else ''}{' + logo' if L.get('logo') else ''}")

    log("6/7 Market regime")
    reg = regime(wide)
    log("  ", reg)

    log("7/7 Writing")

    checks = []

    def build(df, kind, pillars, prevmap):
        items = []
        for p in df.to_dict("records"):
            p = {k: (None if isinstance(v, float) and v != v else v) for k, v in p.items()}
            r = p["_r"]
            cur = r["f"]["currency"] or "USD"
            p["why"] = T.why(kind, p, pillars)
            p["risks"] = T.risks(kind, p, cur)
            p.update({k: r[k] for k in ("name", "exchange", "city", "f")})
            it = bank_item(p, lead.get(r["cik"]), cur, fx) if kind == "banking" else company_item(p, lead.get(r["cik"]), cur, fx, as_of)
            it["rank"] = int(p["rank"])
            if prev_asof:
                it["prevRank"] = prevmap.get(p["ticker"])
            it["pillars"] = [
                {"key": k, "label": lab, "weight": w, "score": round(float(p["p_" + k]))}
                for k, lab, w in pillars if p.get("p_" + k) == p.get("p_" + k) and p.get("p_" + k) is not None
            ]
            items.append(it)
            checks.append(check_entry(kind, it, r, lead.get(r["cik"]) or {}, pillars, cur, prev_asof))
        return items

    asd = dt.date.fromisoformat(as_of)
    out = {
        "week": str(asd.isocalendar()[1]),
        "asOf": as_of,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "nextUpdate": next_update(asd, now).astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "sources": "SEC EDGAR, Massive, Wikidata, FRED, ECB",
        "regime": reg,
        "banking": build(pb, "banking", C.BANK_PILLARS, prev["banking"]),
        "company": build(pc, "company", C.COMPANY_PILLARS, prev["company"]),
    }
    if not out["regime"]:
        del out["regime"]
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1, ensure_ascii=False)
    hist = os.path.join(os.path.dirname(a.out) or ".", "history")
    os.makedirs(hist, exist_ok=True)
    y, w, _ = asd.isocalendar()
    json.dump(out, open(os.path.join(hist, f"{y}-W{w:02d}.json"), "w"), indent=1, ensure_ascii=False)

    # transparency: the full ranking (scores only, no prices)
    full = {}
    for name, d in (("banking", banks), ("company", comps)):
        d = d.dropna(subset=["score"]).sort_values("score", ascending=False).head(30)
        full[name] = [
            {"place": i + 1, "ticker": r.ticker, "country": r.country, "sector": r.sector, "score": round(r.score),
             **{c[2:]: round(getattr(r, c)) for c in d.columns if c.startswith("p_") and getattr(r, c) == getattr(r, c)}}
            for i, r in enumerate(d.itertuples())
        ]
    json.dump({"asOf": as_of, **full}, open(os.path.join(os.path.dirname(a.out) or ".", "eb-ranking-full.json"), "w"), indent=1)
    write_check(os.path.join(os.path.dirname(a.out) or ".", "CHECK.md"), out, checks, reg)
    log(f"Done in {(time.time() - t0) / 60:.0f} min, {massive.calls} price calls.")


if __name__ == "__main__":
    sys.exit(main())
