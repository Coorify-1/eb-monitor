"""EB Islamic Investment: daily update (midnight New York).

python -m islamic.run --out docs/eb-islamic.json --cache cache-islamic
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import time
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from engine import prices as P
from engine import sources as SRC
from engine import texts as T
from engine.run import country_from_sec

from . import config as C
from . import funds as F
from . import index as IX
from . import lists as L
from . import news as N
from . import rates as R
from . import screen as S

NY = ZoneInfo("America/New_York")


SCREEN_VERSION = 3


def log(*a):
    print(*a, flush=True)


def last_finished_day(now_ny):
    d = now_ny.date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def next_midnight(now_ny):
    d = now_ny.date() + dt.timedelta(days=1)
    return dt.datetime.combine(d, dt.time(0, 0), NY)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def seed_prices(cache, seed):
    """First run: start from EB Monitor's price cache (same Massive data) to save an hour."""
    if os.path.exists(os.path.join(cache, "prices.parquet")) or not seed or not os.path.isdir(seed):
        return
    os.makedirs(cache, exist_ok=True)
    for f in ("prices.parquet", "prices_meta.json", "details.json"):
        if os.path.exists(os.path.join(seed, f)):
            shutil.copy(os.path.join(seed, f), os.path.join(cache, f))
            log(f"  seeded {f} from EB Monitor")


# ---------------------------------------------------------------- screen

def refresh_universe(sec, massive, mom, today, state, cache_dir):
    """Weekly: who is in the universe and the balance-sheet figures of each company."""
    tick = pd.DataFrame(sec.tickers())
    tick = tick[tick["exchange"].isin(["NYSE", "Nasdaq"])].dropna(subset=["ticker"])
    tick["tm"] = tick["ticker"].str.replace("-", ".", regex=False)
    u = tick.merge(mom, left_on="tm", right_index=True)
    u = u.sort_values("adv", ascending=False).drop_duplicates("cik").head(C.CANDIDATES)
    log(f"  {len(u)} candidates")
    got = S.domestic_figures(sec, today, log=log)
    det_path = os.path.join(cache_dir, "details.json")
    details = load(det_path, {})
    budget = 40
    state.pop("subs", None)
    subs = state.setdefault("subs2", {})
    rows = []
    def sub_of(cik):
        s = subs.get(str(cik))
        if not s or s.get("at", "") < (today - dt.timedelta(days=30)).isoformat():
            sub = sec.submissions(cik)
            if not sub:
                return None
            forms = set((sub.get("filings") or {}).get("recent", {}).get("form", [])[:200])
            try:
                sic = int(sub.get("sic") or 0)
            except ValueError:
                sic = 0
            country, _ = country_from_sec(sub)
            s = {"sic": sic, "foreign": bool(forms & {"20-F", "40-F", "6-K"}), "cc": country or "",
                 "at": today.isoformat(), "fund": sic == 0 or sic == 6770}
            subs[str(cik)] = s
        return s

    for c in u.itertuples():
        cik = int(c.cik)
        sh = S.shares_of(got, cik, today)
        s = None
        if sh and sh * c.close >= C.MIN_MARKET_CAP_USD * 0.9:
            s = sub_of(cik)
            if s and s.get("foreign"):
                sh = None  # SEC share counts of foreign companies are ordinary shares, not the ADRs that trade here
        mc = sh * c.close if sh else None
        det = None
        if mc is None:
            d = details.get(c.ticker)
            stale = not d or d.get("at", "") < (today - dt.timedelta(days=60)).isoformat()
            if stale and budget > 0:
                try:
                    x = massive.details(c.tm)
                    if x.get("market_cap"):
                        d = {"mc": x["market_cap"], "close": c.close, "at": today.isoformat()}
                        details[c.ticker] = d
                except Exception as e:
                    log("    details failed", c.ticker, e)
                budget -= 1
            if d and d.get("mc") and d.get("close"):
                det = d
                mc = d["mc"] * c.close / d["close"]
        if not mc or mc < C.MIN_MARKET_CAP_USD * 0.9:
            continue
        s = s or sub_of(cik)
        if not s or s.get("fund") or not s.get("sic"):
            continue
        rows.append({"t": c.ticker, "tm": c.tm, "cik": cik, "n": c.name, "sic": s["sic"], "foreign": s["foreign"],
                     "cc": s["cc"], "shares": sh, "det": det})
    json.dump(details, open(det_path, "w"))
    fx = fx_rates()
    state.pop("ffacts", None)
    facts_cache = state.setdefault("facts2", {})
    for r in rows:
        if not r["foreign"] and r["shares"] is not None:
            r["inp"] = S.domestic_ratios_inputs(got, r["cik"], today)
            if r["inp"].get("debt") is not None or r["inp"].get("cash") is not None:
                continue
        fc = facts_cache.get(str(r["cik"]))
        if not fc or fc.get("at", "") < (today - dt.timedelta(days=6)).isoformat():
            facts = sec.facts(r["cik"])
            inp = S.facts_inputs(facts, fx, today) if facts else {}
            facts_cache[str(r["cik"])] = {"at": today.isoformat(), "inp": inp}
        r["inp"] = facts_cache[str(r["cik"])]["inp"]
    log(f"  universe: {len(rows)} companies (market value > $9bn), {sum(r['foreign'] for r in rows)} foreign")
    return rows


def company_name(x):
    n = re.sub(r"\s*/[A-Z]{0,4}/?\s*$", "", T.nice_name(x or "")).strip()
    return re.sub(r"\bELI\b", "Eli", n)


def fx_rates():
    """Units per USD: ECB rates, completed with a free daily feed for currencies the ECB does not publish (TWD, SAR...)."""
    fx = SRC.fx_per_usd()
    try:
        r = SRC.get(C.FX_FALLBACK, timeout=30)
        for k, v in (r.json().get("usd") or {}).items():
            if v and k.upper() not in fx:
                fx[k.upper()] = float(v)
    except Exception as e:
        log("  fx fallback failed:", e)
    return fx


def daily_screen(rows, wide, closes):
    out = []
    for r in rows:
        tm = r["tm"]
        c = closes.get(tm)
        if not c:
            continue
        if r.get("shares"):
            mc = r["shares"] * c
        elif r.get("det"):
            mc = r["det"]["mc"] * c / r["det"]["close"]
        else:
            continue
        s = wide[tm].dropna().iloc[-252:] if tm in wide.columns else pd.Series(dtype=float)
        avg = mc * float(s.mean()) / c if len(s) >= 60 else mc
        ex = S.business_exclusion(r["t"], r["sic"])
        k = S.classify(r.get("inp") or {}, avg, ex)
        out.append({
            "t": r["t"], "tm": tm, "n": company_name(r["n"]), "sec": S.sector_of(r["sic"], r["t"]), "cc": r["cc"], "foreign": r["foreign"],
            "mcap": mc, "mcapAvg": avg, **k, "pur": S.purification(k["npi"]) if k["status"] in ("Halal", "Watch") else None,
            "asOf": (r.get("inp") or {}).get("asOf"),
        })
    big = [x for x in out if x["mcap"] >= C.MIN_MARKET_CAP_USD]
    big.sort(key=lambda x: -x["mcap"])
    return big


def sector_table(rows):
    sec = {}
    for r in rows:
        if r["status"] == "No data":
            continue
        d = sec.setdefault(r["sec"], {"name": r["sec"], "total": 0, "halal": 0, "watch": 0, "not": 0, "excluded": 0})
        d["total"] += 1
        d[{"Halal": "halal", "Watch": "watch", "Not halal": "not", "Excluded": "excluded"}[r["status"]]] += 1
    out = list(sec.values())
    for d in out:
        d["pct"] = round((d["halal"] + d["watch"]) / d["total"] * 100, 1) if d["total"] else 0
    return sorted(out, key=lambda d: -d["pct"])


def changes(prev_status, rows, today):
    out = []
    for r in rows:
        p = prev_status.get(r["t"])
        if p and p != r["status"] and "No data" not in (p, r["status"]):
            out.append({"t": r["t"], "n": r["n"], "from": p, "to": r["status"], "date": today})
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/eb-islamic.json")
    ap.add_argument("--cache", default="cache-islamic")
    ap.add_argument("--seed", default="seed")
    a = ap.parse_args()
    t0 = time.time()
    now = dt.datetime.now(NY)
    today = now.date()
    prev_out = load(a.out, {})
    force = os.environ.get("FORCE") == "true" or os.environ.get("GITHUB_EVENT_NAME") in ("push", "workflow_dispatch")
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and not force:
        if now.hour >= 6:
            log("Not midnight in New York: waiting for the next scheduled run.")
            return
        if prev_out.get("runDate") == today.isoformat():
            log("Today's update is already published.")
            return
    os.makedirs(a.cache, exist_ok=True)
    st_path = os.path.join(a.cache, "state.json")
    state = load(st_path, {})
    seed_prices(a.cache, a.seed)
    sec = SRC.SEC()
    check = []

    log("1/7 Prices (Massive, end of day)")
    day = last_finished_day(now)
    massive = None
    try:
        massive = SRC.Massive()
        df = P.update(a.cache, massive, day, log=log)
    except Exception as e:
        log("  price update failed, using the stored prices:", e)
        df = pd.read_parquet(os.path.join(a.cache, "prices.parquet"))
    wide, vol = P.series_by_ticker(df)
    mom = P.momentum_table(wide, vol)
    closes = {t: float(wide[t].dropna().iloc[-1]) for t in wide.columns if wide[t].notna().any()}
    market_date = str(wide.index[-1])
    log(f"  {len(closes)} tickers, last close {market_date}")

    log("2/7 Halal screen (SEC filings, AAOIFI Standard 21)")
    sc = state.setdefault("screen", {})
    if sc.get("v") != SCREEN_VERSION:  # method changed: rebuild the universe, the index and the change log
        sc.clear()
        state["index"] = {}
        sc["v"] = SCREEN_VERSION
    if not sc.get("rows") or sc.get("at", "") < (today - dt.timedelta(days=6)).isoformat() or os.environ.get("REFRESH") == "true":
        sc["rows"] = refresh_universe(sec, massive, mom, today, state, a.cache)
        sc["at"] = today.isoformat()
    rows = daily_screen(sc["rows"], wide, closes)
    prev_status = sc.get("status") or {}
    ch = changes(prev_status, rows, today.isoformat())
    sc["status"] = {r["t"]: r["status"] for r in rows}
    sc["changes"] = (ch + (sc.get("changes") or []))[:40]
    counts = {k: sum(r["status"] == k for r in rows) for k in ("Halal", "Watch", "Not halal", "Excluded", "No data")}
    log(f"  {len(rows)} companies: {counts}")

    log("3/7 EB Shariah US 100")
    halal = [r for r in rows if r["status"] in ("Halal", "Watch")][: C.INDEX_MEMBERS]
    market = rows[: C.INDEX_MEMBERS]
    ix = IX.extend(state.get("index") or {}, wide, IX.implied_shares(halal, closes), IX.implied_shares(market, closes),
                   today.isoformat())
    state["index"] = ix
    tot = sum(r["mcap"] for r in halal) or 1
    wts = IX.capped(pd.Series({r["t"]: r["mcap"] for r in halal}))
    log(f"  {len(ix.get('series', []))} days, members {len(halal)}")

    log("4/7 Islamic funds (SEC Form N-PORT)")
    mf = state.get("mf")
    if not mf or state.get("mfAt", "") < (today - dt.timedelta(days=30)).isoformat():
        r = sec._get("https://www.sec.gov/files/company_tickers_mf.json", ok404=False)
        j = r.json()
        want = {t for t, *_ in C.FUNDS}
        mf = {}
        for row in j["data"]:
            d = dict(zip(j["fields"], row))
            if d.get("symbol") in want:
                mf[d["symbol"]] = d
        state["mf"], state["mfAt"] = mf, today.isoformat()
    funds = F.update(sec, mf, state.setdefault("funds", {}), log=log)

    log("5/7 Official Shariah lists")
    lc = state.setdefault("lists", {})
    official = {}
    for code, fn in (("MY", L.malaysia), ("ID", L.indonesia), ("AE", L.dubai)):
        try:
            x = fn(lc, log=log)
        except Exception as e:
            log(f"    {code} failed: {e}")
            x = lc.get(code)
        if x:
            lc[code] = x
            official[code] = {k: v for k, v in x.items() if not k.startswith("_")}
            official[code]["banks"] = L.islamic_banks(x)

    log("6/7 Islamic interbank rate (Bank Negara Malaysia)")
    try:
        rates = R.update(state.setdefault("rates", {}), today, log=log)
    except Exception as e:
        log("  rates failed:", e)
        rates = prev_out.get("rates")

    log("7/7 News (GDELT)")
    news, fresh = N.update(state.setdefault("news", {}), log=log)

    series = ix.get("series") or []
    pr = IX.period_returns(series)
    out = {
        "sample": False,
        "version": 1,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "runDate": today.isoformat(),
        "marketDate": market_date,
        "nextUpdate": next_midnight(now).astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        "index": {
            "name": "EB Shariah US 100", "benchmark": "EB US 100",
            "launch": ix.get("launch"), "simulatedBefore": ix.get("simulatedBefore"),
            "members": len(halal), "series": series[-400:], "returns": pr,
            "vol": [IX.volatility(series, 1), IX.volatility(series, 2)],
            "top": [{"t": t, "n": next(r["n"] for r in halal if r["t"] == t), "w": round(float(w) * 100, 2)}
                    for t, w in wts.sort_values(ascending=False).head(10).items()],
            "sectors": sorted([[k, round(float(v) * 100, 1)] for k, v in
                               wts.groupby(lambda t: next(r["sec"] for r in halal if r["t"] == t)).sum().items()],
                              key=lambda kv: -kv[1]),
        },
        "screen": {
            "universe": len(rows), "counts": counts,
            "halalShare": round((counts["Halal"] + counts["Watch"]) / max(1, len(rows) - counts["No data"]) * 100, 1),
            "limits": {"debt": C.DEBT_LIMIT, "cash": C.CASH_LIMIT, "npi": C.NPI_LIMIT},
            "sectors": sector_table(rows),
            "changes": sc["changes"][:20],
            "companies": [{k: (round(v / 1e9, 1) if k in ("mcap", "mcapAvg") and v else v) for k, v in r.items() if k != "tm"}
                          for r in rows],
            "updated": sc.get("at"),
        },
        "funds": funds,
        "official": official,
        "rates": rates,
        "industry": C.INDUSTRY,
        "news": news, "newsFresh": fresh,
    }
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    tmp = a.out + ".tmp"
    json.dump(out, open(tmp, "w"), separators=(",", ":"), default=lambda o: float(o) if isinstance(o, np.floating) else str(o))
    os.replace(tmp, a.out)
    json.dump(state, open(st_path, "w"), separators=(",", ":"), default=str)
    write_check(os.path.join(os.path.dirname(a.out), "eb-islamic-check.md"), out, state, counts, time.time() - t0)
    log(f"Done in {time.time() - t0:.0f} s, {os.path.getsize(a.out) // 1024} KB")


def write_check(path, out, state, counts, secs):
    L_ = ["# EB Islamic Investment — run check", "",
          f"Run {out['generated']} (market close {out['marketDate']}), {secs:.0f} s", "",
          f"Screen: {out['screen']['universe']} companies, {counts}, halal share {out['screen']['halalShare']}%", "",
          "| Ticker | Name | Sector | $bn | Debt % | Cash % | Income % | Status | Why |", "|---|---|---|---|---|---|---|---|---|"]
    for r in out["screen"]["companies"][:40]:
        L_.append(f"| {r['t']} | {r['n'][:28]} | {r['sec']} | {r['mcap']} | {r['debt']} | {r['cash']} | {r['npi']} | {r['status']} | {r['why'][:50]} |")
    L_ += ["", f"Index: {len(out['index']['series'])} days, returns {out['index']['returns']}", "",
           "Top weights: " + ", ".join(f"{x['t']} {x['w']}%" for x in out["index"]["top"]), ""]
    for f in out["funds"]:
        L_.append(f"- Fund {f['t']}: ${f['netAssets']}m as of {f['asOf']}, {len(f['months'])} months, {f['holdings']} holdings")
    for k, v in out["official"].items():
        L_.append(f"- List {k}: {v.get('count')} as of {v.get('asOf')}, sectors {v.get('sectors', [])[:4]}, banks {len(v.get('banks', []))}")
    rt = out.get("rates") or {}
    L_.append(f"- Rates: {len(rt.get('series', []))} days, latest {rt.get('latest')}, OPR {rt.get('opr')}")
    L_.append(f"- News: {len(out['news'])} (fresh: {out['newsFresh']})")
    for n in out["news"][:8]:
        L_.append(f"  - [{n['tag']}] {n['title']} ({n['source']})")
    dbg = (state.get("lists") or {}).get("_debug") or {}
    for k, v in dbg.items():
        L_ += ["", f"## Debug {k}", "```", "\n".join(map(str, v[:120])) if isinstance(v, list) else str(v)[:4000], "```"]
    open(path, "w").write("\n".join(L_) + "\n")


if __name__ == "__main__":
    main()
