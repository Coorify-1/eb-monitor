"""Halal screen of the largest New York listings, from SEC filings (AAOIFI Shari'a Standard No. 21).

Balance-sheet figures come from the SEC "frames" API (one call returns one figure for every
company), so the whole universe needs about a hundred calls a week. Foreign companies that
file 20-F or 40-F reports are read one by one from their company facts.
"""
import datetime as dt

from engine import config as EC
from engine.fundamentals import series as annual_series

from . import config as C


# ---------------------------------------------------------------- periods

def recent_quarters(today: dt.date, n=4):
    """Calendar quarters whose end is at least 40 days old (reports are filed by then)."""
    out = []
    y, q = today.year, (today.month - 1) // 3 + 1
    while len(out) < n:
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        end = dt.date(y, q * 3, 1) + dt.timedelta(days=31)
        end = end.replace(day=1) - dt.timedelta(days=1)
        if (today - end).days >= 40:
            out.append(f"CY{y}Q{q}I")
    return out


def recent_years(today: dt.date):
    y = today.year - 1 if today.month >= 4 else today.year - 2
    return [f"CY{y}", f"CY{y - 1}"]


# ---------------------------------------------------------------- SEC frames

def frame(sec, tax, tag, unit, period):
    r = sec._get(f"https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{unit}/{period}.json")
    if r is None:
        return {}
    out = {}
    for d in (r.json().get("data") or []):
        out[int(d["cik"])] = (d.get("end") or "", float(d["val"]))
    return out


def latest_by_cik(sec, tags, periods, tax="us-gaap", unit="USD", log=print):
    """{cik: (end, value, tag)}: freshest value across tags (earlier tags win ties)."""
    best = {}
    for rank, tag in enumerate(tags):
        for per in periods:
            try:
                f = frame(sec, tax, tag, unit, per)
            except Exception as e:
                log(f"    frame {tag} {per} failed: {e}")
                continue
            for cik, (end, val) in f.items():
                cur = best.get(cik)
                if cur is None or end > cur[0] or (end == cur[0] and rank < cur[3]):
                    best[cik] = (end, val, tag, rank)
    return {k: v[:3] for k, v in best.items()}


def domestic_figures(sec, today, log=print):
    """Every figure needed for the screen, for every US filer, keyed by CIK."""
    qs = recent_quarters(today)
    ys = recent_years(today)
    log(f"    quarters {qs}, years {ys}")
    got = {}
    for bucket, tags in {**C.DEBT_TAGS, **C.CASH_TAGS}.items():
        got[bucket] = latest_by_cik(sec, tags, qs, log=log)
    sh = {}
    for tax, tag in C.SHARES_TAGS:
        x = latest_by_cik(sec, [tag], qs, tax=tax, unit="shares", log=log)
        for cik, v in x.items():
            if cik not in sh or v[0] > sh[cik][0]:
                sh[cik] = v
    got["shares"] = sh
    got["revenue"] = latest_by_cik(sec, C.REVENUE_TAGS, ys, log=log)
    got["interest"] = latest_by_cik(sec, C.INTEREST_INCOME_TAGS, ys, log=log)
    return got


def _v(got, bucket, cik, min_end):
    x = got.get(bucket, {}).get(cik)
    if not x or x[0] < min_end:
        return None, None
    return x[1], x[2]


def domestic_ratios_inputs(got, cik, today):
    """Interest-bearing debt, cash + interest-bearing securities, revenue, interest income (USD)."""
    min_bs = (today - dt.timedelta(days=460)).isoformat()
    min_fl = (today - dt.timedelta(days=820)).isoformat()
    ltn, _ = _v(got, "lt_noncurrent", cik, min_bs)
    ltt, _ = _v(got, "lt_total", cik, min_bs)
    ltc, _ = _v(got, "lt_current", cik, min_bs)
    dc, _ = _v(got, "debt_current", cik, min_bs)
    st, _ = _v(got, "short", cik, min_bs)
    if ltn is not None:
        debt = ltn + (dc if dc is not None else (ltc or 0) + (st or 0))
    elif ltt is not None:
        debt = (ltt - (ltc or 0) + dc) if dc is not None else ltt + (st or 0)
    elif dc is not None or st is not None:
        debt = dc if dc is not None else st
    else:
        debt = None
    cash, ctag = _v(got, "cash", cik, min_bs)
    sti, _ = _v(got, "st_inv", cik, min_bs)
    lti, _ = _v(got, "lt_inv", cik, min_bs)
    if ctag == "CashCashEquivalentsAndShortTermInvestments":
        sti = None
    cash_all = None if cash is None and sti is None else (cash or 0) + (sti or 0) + (lti or 0)
    rev, _ = _v(got, "revenue", cik, min_fl)
    inc, _ = _v(got, "interest", cik, min_fl)
    ends = [got[b][cik][0] for b in ("lt_noncurrent", "lt_total", "cash") if cik in got.get(b, {})]
    return {
        "debt": debt, "cash": cash_all, "revenue": rev, "interest": inc,
        "asOf": max(ends) if ends else None,
        "noDebtTag": debt is None and cash_all is not None,
    }


def shares_of(got, cik, today):
    x = got.get("shares", {}).get(cik)
    if not x or x[0] < (today - dt.timedelta(days=460)).isoformat():
        return None
    return x[1]


# ---------------------------------------------------------------- foreign filers (IFRS, annual)

def _ifrs_latest(facts, tags):
    best = None
    for tag in tags:
        c = ((facts.get("facts") or {}).get("ifrs-full") or {}).get(tag)
        if not c:
            continue
        for unit, rows in (c.get("units") or {}).items():
            for r in rows:
                if r.get("form") not in ("20-F", "20-F/A", "40-F", "40-F/A", "6-K"):
                    continue
                end = r.get("end") or ""
                if best is None or end > best[0]:
                    best = (end, float(r["val"]), unit)
    return best


def foreign_inputs(facts, fx):
    """Same inputs for a 20-F / 40-F filer, converted to USD (fx = units per USD)."""
    def usd(x):
        if not x:
            return None
        rate = fx.get(x[2])
        return x[1] / rate if rate else None

    debt_parts = [_ifrs_latest(facts, [t]) for t in C.IFRS["debt"][:2]]
    if any(debt_parts):
        debt = sum(usd(p) or 0 for p in debt_parts if p)
    else:
        b = _ifrs_latest(facts, C.IFRS["debt"][2:])
        debt = usd(b)
    cash = usd(_ifrs_latest(facts, C.IFRS["cash"]))
    inv = usd(_ifrs_latest(facts, C.IFRS["inv"]))
    rev = usd(_ifrs_latest(facts, C.IFRS["revenue"]))
    inc = usd(_ifrs_latest(facts, C.IFRS["interest"]))
    if rev is None:  # some foreign filers report in US GAAP
        s = annual_series(facts, "revenue")
        rev = s[0][1] / (fx.get(s[0][2]) or 1) if s else None
    cash_all = None if cash is None and inv is None else (cash or 0) + (inv or 0)
    a = _ifrs_latest(facts, C.IFRS["cash"])
    return {"debt": debt, "cash": cash_all, "revenue": rev, "interest": inc,
            "asOf": a[0] if a else None, "noDebtTag": debt is None and cash_all is not None}


# ---------------------------------------------------------------- business and ratio tests

def business_exclusion(ticker, sic):
    t = (ticker or "").upper()
    if t in C.EXCLUDED_TICKERS:
        return C.EXCLUDED_TICKERS[t]
    for lo, hi, why in C.EXCLUDED_SIC:
        if sic and lo <= int(sic) <= hi:
            if int(sic) == 6798:
                return None
            return why
    return None


def classify(inp, mcap_avg, excluded):
    """Ratios in % and the status: Halal, Watch, Not halal, Excluded or No data."""
    out = {"debt": None, "cash": None, "npi": None, "status": "No data", "why": ""}
    if excluded:
        out.update(status="Excluded", why=excluded)
        return out
    if not mcap_avg or mcap_avg <= 0:
        return out
    debt = 0.0 if inp.get("noDebtTag") else inp.get("debt")
    if debt is not None:
        out["debt"] = round(debt / mcap_avg * 100, 2)
    if inp.get("cash") is not None:
        out["cash"] = round(inp["cash"] / mcap_avg * 100, 2)
    rev, inc = inp.get("revenue"), inp.get("interest")
    if rev and rev > 0 and inc is not None:
        out["npi"] = round(max(0.0, inc) / rev * 100, 2)
    if out["debt"] is None and out["cash"] is None:
        return out
    fails, watch = [], []
    for k, lim, m, label in (("debt", C.DEBT_LIMIT, C.WATCH_MARGIN, "Debt"), ("cash", C.CASH_LIMIT, C.WATCH_MARGIN, "Cash"),
                             ("npi", C.NPI_LIMIT, 1.0, "Interest income")):
        v = out[k]
        if v is None:
            continue
        if v >= lim:
            fails.append(f"{label} {v:.1f}% (limit {lim:.0f}%)")
        elif v >= lim - m:
            watch.append(f"{label} close to the limit")
    if fails:
        out.update(status="Not halal", why="; ".join(fails))
    elif watch:
        out.update(status="Watch", why="; ".join(watch))
    else:
        out.update(status="Halal", why="All ratios within limits")
    return out


def purification(npi):
    """Share of each dividend to give away, in % (interest income / revenue)."""
    return None if npi is None else round(npi, 2)


def sector_of(sic):
    s = EC.sector_of(sic)
    return "Financials" if s == "Banks" else s
