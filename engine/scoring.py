"""EB Method: metrics, pillar scores (0-100 vs. peers), EB Score and the weekly picks."""
import math

import numpy as np
import pandas as pd

from . import config as C
from .fundamentals import years_of

INF = float("inf")
TAX = 0.21


def _f(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _div(a, b):
    a, b = _f(a), _f(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def _mult(a, b):
    """Price multiple: negative or zero earnings count as the most expensive."""
    a, b = _f(a), _f(b)
    if a is None or b is None:
        return None
    return a / b if b > 0 else INF


def _ratio(x):
    x = _f(x)
    if x is None:
        return None
    return x / 100 if x > 1.5 else x  # some filers tag 14.2 instead of 0.142


# ---------------------------------------------------------------- metrics

def bank_metrics(c):
    t, p = c["f"]["t"], c["f"]["p"]
    mcap = c["mcap_local"]
    tang = None
    if _f(t.get("equity")) is not None:
        tang = t["equity"] - (t.get("goodwill") or 0) - (t.get("intangibles") or 0)
    eq_avg = np.nanmean([x for x in (_f(t.get("equity")), _f(p.get("equity"))) if x is not None] or [np.nan])
    income = (_f(t.get("net_interest_income")) or 0) + (_f(t.get("noninterest_income")) or 0)
    m = {
        "ptb": _mult(mcap, tang),
        "pe": _mult(mcap, t.get("net_income")),
        "cet1": _ratio(t.get("cet1_ratio")) or _ratio(t.get("tier1_ratio")),
        "tang_lev": _div(tang, t.get("assets")),
        "npl": _div(t.get("nonaccrual"), t.get("loans")),
        "cost_of_risk": _div(t.get("provision"), t.get("loans")),
        "roe": _div(t.get("net_income"), eq_avg if eq_avg == eq_avg else None),
        "roa": _div(t.get("net_income"), t.get("assets")),
        "cost_income": _div(t.get("noninterest_expense"), income) if income > 0 else None,
        "loans_deposits": _div(t.get("loans"), t.get("deposits")),
        # year-on-year, for the reader
        "pretax_chg": _chg(t.get("pretax_income") or t.get("net_income"), p.get("pretax_income") or p.get("net_income")),
        "cet1_prev": _ratio(p.get("cet1_ratio")) or _ratio(p.get("tier1_ratio")),
        "roe_prev": _div(p.get("net_income"), p.get("equity")),
        "npl_prev": _div(p.get("nonaccrual"), p.get("loans")),
    }
    m.update(c["mom"])
    return m


def _chg(a, b):
    a, b = _f(a), _f(b)
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1) * (1 if b > 0 else -1)


def piotroski(t, p):
    sig = []

    def add(cond):
        if cond is not None:
            sig.append(1 if cond else 0)

    roa, roa_p = _div(t.get("net_income"), t.get("assets")), _div(p.get("net_income"), p.get("assets"))
    add(None if roa is None else roa > 0)
    add(None if _f(t.get("cfo")) is None else t["cfo"] > 0)
    add(None if roa is None or roa_p is None else roa > roa_p)
    add(None if _f(t.get("cfo")) is None or _f(t.get("net_income")) is None else t["cfo"] > t["net_income"])
    lev, lev_p = _div(t.get("debt_long"), t.get("assets")), _div(p.get("debt_long"), p.get("assets"))
    add(None if lev is None or lev_p is None else lev <= lev_p)
    cr, cr_p = _div(t.get("current_assets"), t.get("current_liabilities")), _div(p.get("current_assets"), p.get("current_liabilities"))
    add(None if cr is None or cr_p is None else cr > cr_p)
    gm, gm_p = _div(t.get("gross_profit"), t.get("revenue")), _div(p.get("gross_profit"), p.get("revenue"))
    add(None if gm is None or gm_p is None else gm > gm_p)
    at, at_p = _div(t.get("revenue"), t.get("assets")), _div(p.get("revenue"), p.get("assets"))
    add(None if at is None or at_p is None else at > at_p)
    if len(sig) < 5:
        return None
    return sum(sig) / len(sig) * 9


def company_metrics(c):
    f = c["f"]
    t, p = f["t"], f["p"]
    mcap = c["mcap_local"]
    debt = (_f(t.get("debt_long")) or 0) + (_f(t.get("debt_short")) or 0)
    cash = _f(t.get("cash")) or 0
    ebit = _f(t.get("operating_income"))
    if ebit is None and _f(t.get("pretax_income")) is not None:
        ebit = t["pretax_income"] + (_f(t.get("interest_expense")) or 0)
    ebitda = None if ebit is None else ebit + (_f(t.get("da")) or 0)
    capex = abs(_f(t.get("capex")) or 0)
    fcf = None if _f(t.get("cfo")) is None else t["cfo"] - capex
    fcf_p = None if _f(p.get("cfo")) is None else p["cfo"] - abs(_f(p.get("capex")) or 0)
    ev = None if mcap is None else mcap + debt - cash
    invested = (_f(t.get("equity")) or 0) + debt - cash
    revs = years_of(f["hist"], "revenue")
    ops = years_of(f["hist"], "operating_income")
    margins = [o / r for o, r in zip(ops, revs) if r]
    tl = _f(t.get("liabilities"))
    if tl is None and _f(t.get("assets")) is not None and _f(t.get("equity")) is not None:
        tl = t["assets"] - t["equity"]
    ta = _f(t.get("assets"))
    altman = None
    if ta and tl and ebit is not None and _f(t.get("revenue")) is not None and mcap:
        wc = (_f(t.get("current_assets")) or 0) - (_f(t.get("current_liabilities")) or 0)
        re_ = _f(t.get("retained_earnings")) or 0
        altman = 1.2 * wc / ta + 1.4 * re_ / ta + 3.3 * ebit / ta + 0.6 * mcap / tl + 1.0 * t["revenue"] / ta
    m = {
        "fcf_yield": _div(fcf, mcap),
        "ev_ebit": _mult(ev, ebit),
        "roic": _div(None if ebit is None else ebit * (1 - TAX), invested) if invested > 0 else None,
        "margin_std": float(np.std(margins)) if len(margins) >= 3 else None,
        "nd_ebitda": (None if ebitda is None else ((debt - cash) / ebitda if ebitda > 0 else INF)),
        "piotroski": piotroski(t, p),
        "altman": altman,
        # for the reader
        "revenue_chg": _chg(t.get("revenue"), p.get("revenue")),
        "ebit_chg": _chg(ebit, _f(p.get("operating_income"))),
        "fcf": fcf,
        "fcf_chg": _chg(fcf, fcf_p),
        "ebit": ebit,
        "nd_ebitda_prev": _nd_prev(p),
    }
    m.update(c["mom"])
    return m


def _nd_prev(p):
    debt = (_f(p.get("debt_long")) or 0) + (_f(p.get("debt_short")) or 0)
    e = _f(p.get("operating_income"))
    if e is None:
        return None
    eb = e + (_f(p.get("da")) or 0)
    return (debt - (_f(p.get("cash")) or 0)) / eb if eb > 0 else None


# ---------------------------------------------------------------- scores

# pillar -> list of (metric, higher_is_better, weight)
BANK_PARTS = {
    "valuation": [("ptb", False, 0.6), ("pe", False, 0.4)],
    "momentum": [("mom_12_1", True, 0.7), ("trend_200", True, 0.3)],
    "capital": [("cet1", True, 0.6), ("tang_lev", True, 0.4)],
    "quality": [("npl", False, 0.6), ("cost_of_risk", False, 0.4)],
    "profit": [("roe", True, 0.6), ("roa", True, 0.4)],
}
COMPANY_PARTS = {
    "valuation": [("fcf_yield", True, 0.5), ("ev_ebit", False, 0.5)],
    "momentum": [("mom_12_1", True, 0.7), ("trend_200", True, 0.3)],
    "quality": [("roic", True, 0.7), ("margin_std", False, 0.3)],
    "health": [("nd_ebitda", False, 0.4), ("piotroski", True, 0.3), ("altman", True, 0.3)],
}


def pct_rank(s: pd.Series, higher=True) -> pd.Series:
    s = s.astype(float)
    ok = s.notna()
    n = ok.sum()
    out = pd.Series(np.nan, index=s.index)
    if n == 0:
        return out
    r = s[ok].rank(method="average")
    p = (r - 0.5) / n * 100
    out[ok] = p if higher else 100 - p
    return out


def score(df: pd.DataFrame, parts, pillars, group_col=None, min_group=8):
    """Adds pillar columns (0-100) and 'score'. Ranks within group_col when the group is big enough."""
    df = df.copy()
    comp = {}
    for pil, items in parts.items():
        for metric, higher, _ in items:
            col = df[metric] if metric in df else pd.Series(np.nan, index=df.index)
            if group_col and pil != "momentum":
                g = df[group_col]
                big = g.map(g.value_counts()) >= min_group
                r_all = pct_rank(col, higher)
                r_grp = col.groupby(g).transform(lambda x: pct_rank(x, higher))
                comp[metric] = r_grp.where(big, r_all)
            else:
                comp[metric] = pct_rank(col, higher)
    for pil, items in parts.items():
        num = pd.Series(0.0, index=df.index)
        den = pd.Series(0.0, index=df.index)
        for metric, _, w in items:
            v = comp[metric]
            num += v.fillna(0) * w
            den += v.notna() * w
        df["p_" + pil] = (num / den).where(den > 0)
    wsum = sum(w for _, _, w in pillars)
    num = pd.Series(0.0, index=df.index)
    have = pd.Series(0.0, index=df.index)
    for key, _, w in pillars:
        v = df["p_" + key]
        num += v.fillna(0) * w
        have += v.notna() * w
    df["coverage"] = have / wsum
    df["score"] = (num / have).where(df["coverage"] >= C.MIN_WEIGHT_COVERAGE)
    return df


def pick(df: pd.DataFrame, prev: dict, sector_cap=True):
    """Top 5 with stability (keep last week's picks while in the top 10) and diversification."""
    d = df.dropna(subset=["score"]).sort_values("score", ascending=False).reset_index(drop=True)
    d["place"] = d.index + 1
    chosen, by_c, by_s = [], {}, {}

    def ok(r):
        if by_c.get(r.country, 0) >= C.MAX_PER_COUNTRY:
            return False
        if sector_cap and by_s.get(r.sector, 0) >= C.MAX_PER_SECTOR:
            return False
        return True

    def take(r):
        chosen.append(r.ticker)
        by_c[r.country] = by_c.get(r.country, 0) + 1
        by_s[r.sector] = by_s.get(r.sector, 0) + 1

    for r in d[d.ticker.isin(list(prev)) & (d.place <= C.KEEP_IF_IN_TOP)].itertuples():
        if len(chosen) < C.PICKS and ok(r):
            take(r)
    for r in d.itertuples():
        if len(chosen) >= C.PICKS:
            break
        if r.ticker not in chosen and ok(r):
            take(r)
    # not enough diversity in the data: fill the remaining places by score
    for r in d.itertuples():
        if len(chosen) >= C.PICKS:
            break
        if r.ticker not in chosen:
            take(r)
    out = d[d.ticker.isin(chosen)].sort_values("score", ascending=False).copy()
    out["rank"] = range(1, len(out) + 1)
    return out
