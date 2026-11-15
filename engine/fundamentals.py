"""Annual figures from SEC XBRL company facts (10-K, 20-F, 40-F)."""
import datetime as dt

from .config import FLOW, RATIO, TAGS

ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "10-KT"}


def _d(s):
    return dt.date.fromisoformat(s)


def _annual_points(units, kind):
    """{end_date: (value, filed)} for full-year values (flows) or year-end values (stocks)."""
    pts = {}
    for unit, rows in units.items():
        for r in rows:
            if r.get("form") not in ANNUAL_FORMS:
                continue
            end = r.get("end")
            if not end:
                continue
            if kind == "flow":
                st = r.get("start")
                if not st:
                    continue
                days = (_d(end) - _d(st)).days
                if not 330 <= days <= 380:
                    continue
            filed = r.get("filed", "")
            if end not in pts or filed > pts[end][2]:
                pts[end] = (float(r["val"]), unit, filed)
    return pts


def series(facts, key):
    """Most recent concept that has data: list of (end, value, unit), newest first."""
    kind = "flow" if key in FLOW else "stock"
    best = None
    for tax, concept in TAGS[key]:
        c = ((facts.get("facts") or {}).get(tax) or {}).get(concept)
        if not c:
            continue
        pts = _annual_points(c.get("units") or {}, kind)
        if not pts:
            continue
        latest = max(pts)
        if best is None or latest > best[0]:
            best = (latest, pts)
    if not best:
        return []
    pts = best[1]
    return [(e, v, u) for e, (v, u, _) in sorted(pts.items(), reverse=True)]


def shares_outstanding(facts):
    """Latest cover-page share count (all classes when reported as one figure)."""
    c = ((facts.get("facts") or {}).get("dei") or {}).get("EntityCommonStockSharesOutstanding")
    if not c:
        return None
    rows = [r for u in (c.get("units") or {}).values() for r in u]
    if not rows:
        return None
    rows.sort(key=lambda r: (r.get("end", ""), r.get("filed", "")))
    return float(rows[-1]["val"])


def extract(facts):
    """Latest fiscal year (t) and the year before (p) for every tracked figure."""
    out = {"fy_end": None, "currency": None, "t": {}, "p": {}, "hist": {}}
    for key in TAGS:
        s = series(facts, key)
        if not s:
            continue
        out["hist"][key] = s[:6]
    # anchor year: latest year-end with total assets
    anchor = (out["hist"].get("assets") or [[None]])[0][0]
    if not anchor:
        anchor = max((s[0][0] for s in out["hist"].values()), default=None)
    if not anchor:
        return out
    out["fy_end"] = anchor
    a = _d(anchor)
    for key, s in out["hist"].items():
        for e, v, u in s:
            gap = (a - _d(e)).days
            if abs(gap) <= 45 and key not in out["t"]:
                out["t"][key] = v
                if u not in ("pure", "shares") and out["currency"] is None and key in ("assets", "revenue", "equity"):
                    out["currency"] = u
            elif 320 <= gap <= 410 and key not in out["p"]:
                out["p"][key] = v
    if out["currency"] is None:
        for s in out["hist"].values():
            u = s[0][2]
            if u not in ("pure", "shares"):
                out["currency"] = u
                break
    return out


def years_of(hist, key, n=5):
    return [v for _, v, _ in (hist.get(key) or [])[:n]]
