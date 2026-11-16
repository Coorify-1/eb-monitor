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


# ---------------------------------------------------------------- company facts (one company at a time)

BS_FORMS = {"10-Q", "10-Q/A", "10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "6-K"}
FY_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


def _days(a, b):
    try:
        return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
    except Exception:
        return 0


def _latest(facts, tax, tags, flow=False):
    """(end, value, currency) of the freshest fact among tags; flows must cover about one year."""
    best = None
    for rank, tag in enumerate(tags):
        c = ((facts.get("facts") or {}).get(tax) or {}).get(tag)
        if not c:
            continue
        for unit, rows in (c.get("units") or {}).items():
            if "/" in unit or len(unit) != 3:
                continue
            for r in rows:
                if r.get("form") not in (FY_FORMS if flow else BS_FORMS):
                    continue
                if flow and not 330 <= _days(r.get("start", ""), r.get("end", "")) <= 380:
                    continue
                end = r.get("end") or ""
                if best is None or end > best[0] or (end == best[0] and rank < best[3]):
                    best = (end, float(r["val"]), unit, rank)
    return best[:3] if best else None


def _ever_debt(facts, tax):
    """True when the company has tagged any borrowing in any of its filings (so a missing figure is a gap, not zero)."""
    tags = set(sum(C.DEBT_TAGS.values(), [])) if tax == "us-gaap" else set(C.IFRS["debt_parts"] + C.IFRS["debt_alt"] + ["Borrowings"])
    tags |= {"DebtInstrumentCarryingAmount", "DebtInstrumentFaceAmount", "LongTermDebtFairValue", "LineOfCredit"} if tax == "us-gaap" else {"BondsIssued", "LoansReceived"}
    have = (facts.get("facts") or {}).get(tax) or {}
    return any(t in have for t in tags)


def facts_inputs(facts, fx, today, domestic=False):
    """Screen inputs from one company's facts (US GAAP or IFRS, any currency), in USD.
    Foreign companies report once a year, so balance sheets up to 25 months old are accepted
    (the page shows the balance-sheet date of every company)."""
    min_bs = (today - dt.timedelta(days=760)).isoformat()

    def usd(x, old=min_bs):
        if not x or x[0] < old:
            return None
        rate = fx.get(x[2])
        return x[1] / rate if rate else None

    best = None
    for tax in ("us-gaap", "ifrs-full"):
        if tax == "us-gaap":
            D, K = C.DEBT_TAGS, C.CASH_TAGS
            g = lambda b, flow=False: _latest(facts, tax, D.get(b) or K.get(b) or b, flow)
            ltn, ltt, ltc, dcur, st = (usd(g(b)) for b in ("lt_noncurrent", "lt_total", "lt_current", "debt_current", "short"))
            if ltn is not None:
                debt = ltn + (dcur if dcur is not None else (ltc or 0) + (st or 0))
            elif ltt is not None:
                debt = ltt + (st or 0)
            else:
                debt = dcur if dcur is not None else st
            ca = g("cash")
            cash, sti, lti = usd(ca), usd(g("st_inv")), usd(g("lt_inv"))
            rev = usd(_latest(facts, tax, C.REVENUE_TAGS, True), (today - dt.timedelta(days=1000)).isoformat())
            inc = usd(_latest(facts, tax, C.INTEREST_INCOME_TAGS, True), (today - dt.timedelta(days=1000)).isoformat())
        else:
            I = C.IFRS
            tot = usd(_latest(facts, tax, ["Borrowings"]))
            parts = [usd(_latest(facts, tax, [t])) for t in I["debt_parts"]]
            alt = [usd(_latest(facts, tax, [t])) for t in I["debt_alt"]]
            if tot is not None:
                debt = tot
            elif any(p is not None for p in parts):
                debt = sum(p for p in parts if p is not None)
            elif any(p is not None for p in alt):
                debt = sum(p for p in alt if p is not None)
            else:
                debt = None
            ca = _latest(facts, tax, I["cash"])
            cash, sti, lti = usd(ca), usd(_latest(facts, tax, I["inv"])), None
            rev = usd(_latest(facts, tax, I["revenue"], True), (today - dt.timedelta(days=1000)).isoformat())
            inc = usd(_latest(facts, tax, I["interest"], True), (today - dt.timedelta(days=1000)).isoformat())
        cash_all = None if cash is None and sti is None else (cash or 0) + (sti or 0) + (lti or 0)
        got = {"debt": debt, "cash": cash_all, "revenue": rev, "interest": inc,
               "asOf": ca[0] if ca and cash is not None else None,
               "noDebtTag": debt is None and cash_all is not None and (
                   (domestic and tax == "us-gaap") or not _ever_debt(facts, tax))}
        if cash_all is not None or debt is not None:
            if best is None or (got["asOf"] or "") > (best["asOf"] or ""):
                best = got
    return best or {}


foreign_inputs = None  # replaced by facts_inputs


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
    if out["debt"] is None:  # without the debt figure the screen cannot conclude
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


def sector_of(sic, ticker=None):
    if ticker and ticker.upper() in C.SECTOR_OVERRIDE:
        return C.SECTOR_OVERRIDE[ticker.upper()]
    s = EC.sector_of(sic)
    return "Financials" if s == "Banks" else s
