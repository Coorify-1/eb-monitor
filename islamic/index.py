"""EB Shariah US 100: the 100 largest New York listings that pass the halal screen,
weighted by market value (no company above 8%), compared with the 100 largest listings
without any screen ("EB US 100", same method).

Before the launch date the history is simulated with the members of the launch day;
after it, each day uses the members known that day, so the record is never rewritten.
"""
import numpy as np
import pandas as pd

from . import config as C


def capped(w: pd.Series, cap=C.INDEX_CAP):
    w = w.clip(lower=0)
    if w.sum() <= 0:
        return w
    w = w / w.sum()
    for _ in range(20):
        over = w > cap + 1e-12
        if not over.any():
            break
        extra = (w[over] - cap).sum()
        w[over] = cap
        rest = ~over & (w > 0)
        if not rest.any():
            break
        w[rest] += extra * w[rest] / w[rest].sum()
    return w


def daily_returns(wide: pd.DataFrame, shares: dict, start=None):
    """Index return for each day after `start` (weights from the previous close)."""
    cols = [t for t in shares if t in wide.columns]
    if not cols:
        return pd.Series(dtype=float)
    px = wide[cols].sort_index().ffill(limit=3)
    sh = pd.Series({t: shares[t] for t in cols}, dtype=float)
    out = {}
    dates = list(px.index)
    for i in range(1, len(dates)):
        d0, d1 = dates[i - 1], dates[i]
        if start and d1 <= start:
            continue
        p0, p1 = px.loc[d0], px.loc[d1]
        ok = p0.notna() & p1.notna() & (p0 > 0)
        if ok.sum() < max(5, len(cols) // 3):
            continue
        w = capped((sh[ok] * p0[ok]).astype(float))
        r = (p1[ok] / p0[ok] - 1).clip(-0.5, 1.0)
        out[d1] = float((w * r).sum())
    return pd.Series(out).sort_index()


def extend(state: dict, wide: pd.DataFrame, shariah: dict, market: dict, today: str):
    """Adds the new days to the stored record (or builds it the first time)."""
    series = state.get("series") or []
    if not series:
        rs = daily_returns(wide, shariah)
        rm = daily_returns(wide, market)
        both = pd.concat([rs, rm], axis=1, keys=["s", "m"]).dropna()
        if both.empty:
            return state
        first = both.index[0]
        prev = wide.index[list(wide.index).index(first) - 1] if first in list(wide.index) else first
        s = m = 100.0
        series = [[prev, 100.0, 100.0]]
        for d, row in both.iterrows():
            s *= 1 + row["s"]
            m *= 1 + row["m"]
            series.append([d, round(float(s), 4), round(float(m), 4)])
        state = {"launch": today, "simulatedBefore": today, "series": series}
        return state
    last = series[-1][0]
    rs = daily_returns(wide, shariah, start=last)
    rm = daily_returns(wide, market, start=last)
    both = pd.concat([rs, rm], axis=1, keys=["s", "m"]).dropna()
    s, m = series[-1][1], series[-1][2]
    for d, row in both.iterrows():
        s *= 1 + row["s"]
        m *= 1 + row["m"]
        series.append([d, round(float(s), 4), round(float(m), 4)])
    state["series"] = series[-800:]
    return state


def period_returns(series):
    """Returns over 1 day, 1 week, 1/3/6 months, year to date and 1 year (in %)."""
    if len(series) < 2:
        return {}
    df = pd.DataFrame(series, columns=["d", "s", "m"]).set_index("d")
    last = df.index[-1]
    ld = pd.Timestamp(last)
    out = {}

    def ret(base_date):
        base = df[df.index <= base_date]
        if base.empty:
            return None
        b = base.iloc[-1]
        e = df.iloc[-1]
        return [round(float(e.s / b.s - 1) * 100, 2), round(float(e.m / b.m - 1) * 100, 2)]

    out["1D"] = [round(float(df.s.iloc[-1] / df.s.iloc[-2] - 1) * 100, 2), round(float(df.m.iloc[-1] / df.m.iloc[-2] - 1) * 100, 2)]
    for k, days in (("1W", 7), ("1M", 31), ("3M", 92), ("6M", 183), ("1Y", 365)):
        out[k] = ret((ld - pd.Timedelta(days=days)).strftime("%Y-%m-%d"))
    out["YTD"] = ret(f"{ld.year - 1}-12-31")
    return out


def implied_shares(rows, closes):
    """Index units per company: market value / last close (works for ADRs too)."""
    out = {}
    for r in rows:
        t = r["tm"]
        c = closes.get(t)
        if c and c > 0 and r.get("mcap"):
            out[t] = r["mcap"] / c
    return out


def volatility(series, col=1, days=252):
    v = np.array([p[col] for p in series[-days - 1:]], dtype=float)
    if len(v) < 30:
        return None
    r = np.diff(np.log(v))
    return round(float(r.std() * np.sqrt(252) * 100), 1)
