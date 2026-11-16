"""Islamic money-market rates from Bank Negara Malaysia (Open API).

Source: Bank Negara Malaysia. Data and information are subject to Terms of Use for BNM Datasets.
"""
import datetime as dt
import time

import requests

from . import config as C

H = {"Accept": "application/vnd.BNM.API.v1+json", "User-Agent": "Economic Bearings research"}


def _get(path):
    for i in range(3):
        try:
            r = requests.get(f"{C.BNM_API}/{path}", headers=H, timeout=60)
            if r.status_code == 200:
                return r.json().get("data")
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(3)
    return None


def months_back(today, n):
    y, m = today.year, today.month
    for _ in range(n):
        yield y, m
        m -= 1
        if m == 0:
            y, m = y - 1, 12


def update(cache, today, log=print):
    """cache = {"iir": {date: {...}}, "opr": [[date, level]], "fetched": [...months]}"""
    iir = cache.setdefault("iir", {})
    done = set(cache.setdefault("months", []))
    for y, m in months_back(today, C.RATES_MONTHS):
        key = f"{y}-{m:02d}"
        recent = (today.year, today.month) == (y, m) or (today - dt.date(y, m, 1)).days < 40
        if key in done and not recent:
            continue
        rows = _get(f"islamic-interbank-rate/year/{y}/month/{m}") or []
        for r in rows if isinstance(rows, list) else [rows]:
            if r and r.get("date") and r.get("overnight") is not None:
                iir[r["date"]] = {k: r.get(k) for k in ("overnight", "1_week", "1_month", "3_month")}
        if rows and not recent:
            done.add(key)
        time.sleep(0.5)
    cache["months"] = sorted(done)
    opr = {}
    for y in range(today.year - 3, today.year + 1):
        rows = _get(f"opr/year/{y}") or []
        for r in rows if isinstance(rows, list) else [rows]:
            if r and r.get("date") and r.get("new_opr_level") is not None:
                opr[r["date"]] = r["new_opr_level"]
    if opr:
        cache["opr"] = sorted(opr.items())
    pts = sorted(iir.items())
    log(f"    Islamic interbank rate: {len(pts)} days, last {pts[-1][0] if pts else None}")
    # OPR as a daily step series aligned on the same dates
    steps = cache.get("opr") or []
    out = []
    for d, v in pts:
        lvl = None
        for sd, sv in steps:
            if sd <= d:
                lvl = sv
        out.append([d, round(float(v["overnight"]), 3), lvl])
    last = pts[-1][1] if pts else {}
    return {
        "series": out[-520:],
        "latest": {"date": pts[-1][0] if pts else None, **{k: last.get(k) for k in ("overnight", "1_week", "1_month", "3_month")}},
        "opr": steps[-1][1] if steps else None,
        "oprDate": steps[-1][0] if steps else None,
        "source": "Source: Bank Negara Malaysia. Data and information are subject to Terms of Use for BNM Datasets.",
        "terms": C.BNM_TERMS,
    }
