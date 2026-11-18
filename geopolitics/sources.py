"""GEOPOLITICAL RISK MONITOR — data adapters.

Each function returns plain Python data and never raises: a source that does not answer
returns None and the engine works with what is left. Series are lists of (YYYY-MM-DD, value),
oldest first.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import random
import time

import requests

from analyst import sources as AS   # Google News headlines and the EB Metals Worker, shared with THE ANALYST
from . import config as C

LOG: list[str] = []
BROWSER = AS.BROWSER


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.append(msg)
    print(msg, flush=True)


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ GDELT (world news)

_last_call = [0.0]


def gdelt_timeline(query: str, mode: str, start: dt.date, end: dt.date):
    """Daily values of a GDELT DOC 2.0 timeline.

    mode = "timelinevol"  -> share of all monitored news coverage matching the query (%)
    mode = "timelinetone" -> average tone of that coverage (negative = more negative)
    GDELT accepts about one request every 5 seconds and answers 429 to busy shared machines,
    so calls are spaced and retried with pauses."""
    start = max(start, dt.date.fromisoformat(C.HISTORY_START))
    if start > end:
        return None
    params = {"query": query, "mode": mode, "format": "json",
              "startdatetime": start.strftime("%Y%m%d000000"),
              "enddatetime": end.strftime("%Y%m%d235959")}
    for i in range(8):
        wait = (6 if i == 0 else random.uniform(12, 30)) - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            r = requests.get(C.GDELT_DOC, params=params, timeout=90, headers={"User-Agent": BROWSER})
        except Exception as e:  # noqa: BLE001
            log(f"  GDELT {mode} failed: {str(e)[:80]}")
            continue
        if r.status_code != 200 or not r.text.lstrip().startswith("{"):
            if r.status_code != 429:
                log(f"  GDELT {mode} -> HTTP {r.status_code} {r.text[:80]!r}")
                if r.status_code == 200:      # an answer, but not data (bad query or dates)
                    return None
            continue
        try:
            data = ((r.json().get("timeline") or [{}])[0].get("data")) or []
        except Exception:  # noqa: BLE001
            continue
        daily: dict[str, list[float]] = {}
        for x in data:
            d = str(x.get("date", ""))[:8]
            v = _num(x.get("value"))
            if len(d) == 8 and d.isdigit() and v is not None:
                daily.setdefault(f"{d[:4]}-{d[4:6]}-{d[6:]}", []).append(v)
        return [(d, sum(v) / len(v)) for d, v in sorted(daily.items())]
    log(f"  GDELT {mode}: no answer after 8 tries (busy)")
    return None


def headlines(query: str, n: int = 4):
    """Latest headlines (title, source, link) from Google News, for the short view."""
    try:
        return AS._rss(query)[:n]
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ prices

def fred_series(series_id: str, start: dt.date):
    """A FRED series. First through the Financial Markets Worker (the same FRED data the
    site uses, and fast from GitHub), then the public FRED file as a back-up."""
    for rng in ("5Y", "2Y", "1Y", "6M"):
        s = AS.market_history("FRED:" + series_id, rng)
        if s and len(s) > 40:
            return [p for p in s if p[0] >= start.isoformat()] or s
    try:
        r = requests.get(C.FRED_CSV, params={"id": series_id, "cosd": start.isoformat()},
                         timeout=25, headers={"User-Agent": BROWSER})
        if r.status_code == 200 and "," in r.text:
            rows = list(csv.reader(io.StringIO(r.text)))
            out = [(row[0], _num(row[1])) for row in rows[1:] if len(row) >= 2]
            out = [(d, v) for d, v in out if v is not None and d >= start.isoformat()]
            if out:
                return out
        log(f"  FRED {series_id} -> HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        log(f"  FRED {series_id} failed: {str(e)[:80]}")
    return None


def metals_series(metal: str):
    for rng in ("2y", "1y", "6mo"):
        s = AS.metals_history(metal, rng)
        if s and len(s) > 40:
            return s
    return None
