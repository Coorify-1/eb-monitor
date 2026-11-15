"""Daily closes for US-listed stocks, kept in a cache that grows a few days each week."""
import datetime as dt
import json
import os

import numpy as np
import pandas as pd

KEEP_DOLLAR_VOLUME = 2e6   # store only stocks trading at least $2m that day
HISTORY_DAYS = 400         # calendar days kept (12-month momentum + 200-day average)


def _load(cache_dir):
    p = os.path.join(cache_dir, "prices.parquet")
    m = os.path.join(cache_dir, "prices_meta.json")
    if os.path.exists(p) and os.path.exists(m):
        return pd.read_parquet(p), json.load(open(m))
    return pd.DataFrame(columns=["date", "ticker", "close", "volume"]), {}


def _save(cache_dir, df, meta):
    os.makedirs(cache_dir, exist_ok=True)
    df.to_parquet(os.path.join(cache_dir, "prices.parquet"), index=False)
    json.dump(meta, open(os.path.join(cache_dir, "prices_meta.json"), "w"), indent=1)


def weekdays(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += dt.timedelta(days=1)


def update(cache_dir, massive, last_day: dt.date, always=("SPY",), log=print):
    """Bring the cache up to last_day (the last finished trading day)."""
    df, meta = _load(cache_dir)
    first = last_day - dt.timedelta(days=HISTORY_DAYS)
    have = meta.get("last_date")
    start = dt.date.fromisoformat(have) + dt.timedelta(days=1) if have else first
    start = max(start, first)

    # 1) splits that took effect since the last update (never future ones): adjust stored history
    done = set(meta.get("splits_done", []))
    if have and not meta.get("split_fix_v1"):
        # one-time repair: undo the future splits applied by mistake on 2026-11-15
        n = 0
        for s in massive.splits_since(have):
            t, ex, f, to = s.get("ticker"), s.get("execution_date"), s.get("split_from"), s.get("split_to")
            if t and ex and f and to and ex > have:
                mask = (df["ticker"] == t) & (df["date"] < ex)
                df.loc[mask, "close"] = df.loc[mask, "close"] * (float(to) / float(f))
                df.loc[mask, "volume"] = df.loc[mask, "volume"] * (float(f) / float(to))
                n += 1
        meta["split_fix_v1"] = True
        log(f"  repaired {n} split adjustments")
    if have:
        n = 0
        for s in massive.splits_since(have):
            t, ex, f, to = s.get("ticker"), s.get("execution_date"), s.get("split_from"), s.get("split_to")
            sid = f"{t}|{ex}|{f}|{to}"
            if not (t and ex and f and to) or not (have < ex <= last_day.isoformat()) or sid in done:
                continue
            mask = (df["ticker"] == t) & (df["date"] < ex)
            if mask.any():
                df.loc[mask, "close"] = df.loc[mask, "close"] * (float(f) / float(to))
                df.loc[mask, "volume"] = df.loc[mask, "volume"] * (float(to) / float(f))
                n += 1
            done.add(sid)
        meta["splits_done"] = sorted(done)[-2000:]
        log(f"  splits applied: {n}")

    # 2) new trading days
    days = list(weekdays(start, last_day))
    log(f"  price days to fetch: {len(days)} (about {len(days) * 13 // 60} min)")
    new = []
    for i, d in enumerate(days):
        rows = massive.grouped(d.isoformat())
        if not rows:
            continue  # market holiday
        part = pd.DataFrame(
            {
                "date": d.isoformat(),
                "ticker": [r.get("T") for r in rows],
                "close": [r.get("c") for r in rows],
                "volume": [r.get("v") for r in rows],
            }
        ).dropna()
        keep = (part["close"] * part["volume"] >= KEEP_DOLLAR_VOLUME) | part["ticker"].isin(always)
        new.append(part[keep])
        if (i + 1) % 25 == 0:
            log(f"    {i + 1}/{len(days)} days")
            # save progress so a long first run is never lost
            tmp = pd.concat([df] + new, ignore_index=True)
            _save(cache_dir, tmp, {**meta, "last_date": d.isoformat()})
    if new:
        df = pd.concat([df] + new, ignore_index=True)
    df = df[df["date"] >= first.isoformat()].drop_duplicates(["date", "ticker"], keep="last")
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    meta["last_date"] = last_day.isoformat()
    _save(cache_dir, df, meta)
    return df


def series_by_ticker(df):
    wide = df.pivot(index="date", columns="ticker", values="close").sort_index()
    vol = df.pivot(index="date", columns="ticker", values="volume").sort_index()
    return wide, vol


def momentum_table(wide: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    """Per ticker: last close, 12-1 month return, gap to 200-day average, avg dollar volume."""
    out = {}
    n = len(wide)
    for t in wide.columns:
        s = wide[t].dropna()
        if len(s) < 30:
            continue
        last = s.iloc[-1]
        r = {"close": float(last), "date": s.index[-1]}
        if len(s) >= 230:
            p_skip = s.iloc[-22] if len(s) > 22 else np.nan
            p_year = s.iloc[max(0, len(s) - 253)]
            r["mom_12_1"] = float(p_skip / p_year - 1) if p_year > 0 else np.nan
            r["ret_12m"] = float(last / p_year - 1) if p_year > 0 else np.nan
        if len(s) >= 150:
            ma = s.iloc[-200:].mean()
            r["trend_200"] = float(last / ma - 1) if ma > 0 else np.nan
        v = vol[t].dropna()
        dv = (s.iloc[-20:] * v.reindex(s.index).iloc[-20:]).mean()
        r["adv"] = float(dv) if dv == dv else 0.0
        r["days"] = len(s)
        out[t] = r
    return pd.DataFrame.from_dict(out, orient="index")
