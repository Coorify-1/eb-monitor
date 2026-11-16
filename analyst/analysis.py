"""THE ANALYST — the analysis itself (rules, no AI).

1. Each asset: last value, 1-day / 1-week / 1-month change, and the size of today's
   move compared with its usual daily swing (z-score).
2. Market regime: which pattern fits today's moves best (risk-off, inflation scare…).
3. Themes: a news theme is "confirmed" only if its news volume jumps AND at least two
   of the markets it usually moves went the expected way.
4. The lead story, the two charts and the facts handed to the writer.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics

from . import config as C

# ------------------------------------------------------------------ formatting


def sgn(v):
    return "+" if v > 0 else "−" if v < 0 else ""


def fmt_pct(v, d=1):
    if v is None:
        return "—"
    if abs(v) < 0.05 and d == 1:
        d = 2
    return f"{sgn(v)}{abs(v):.{d}f}%"


def fmt_bp(v):
    if v is None:
        return "—"
    return f"{sgn(round(v))}{abs(round(v))} bp"


def fmt_level(a: dict, v):
    if v is None:
        return "—"
    if a["kind"] == "yield":
        return f"{v:.2f}%"
    if a["cls"] == "fx":
        return f"{v:.4f}" if v < 20 else f"{v:.2f}"
    d = 0 if v >= 10000 else 2 if v < 1000 else 0
    s = f"{v:,.{d}f}"
    s = ("$" + s) if a["unit"] == "$" else s
    return s + "/t" if a.get("id") in ("copper",) else s


def fmt_move(a: dict, v):
    return fmt_bp(v) if a["kind"] == "yield" else fmt_pct(v)


SESSION_DATE = ""  # date of the session the edition is about (set by run.py)


def lag_note(asof) -> str:
    """' (latest data: Nov 12)' when a market's data is older than the session analysed."""
    if not asof or not SESSION_DATE or asof >= SESSION_DATE:
        return ""
    try:
        d = dt.date.fromisoformat(asof)
    except ValueError:
        return ""
    return f" (latest data: {d.strftime('%b')} {d.day})"


# ------------------------------------------------------------------ per-asset statistics


def _changes(series, kind):
    vals = [v for _, v in series]
    out = []
    for i in range(1, len(vals)):
        a, b = vals[i - 1], vals[i]
        if kind == "yield":
            out.append((b - a) * 100)
        elif a > 0 and b > 0:
            out.append(math.log(b / a) * 100)
    return out


def _back(series, n, kind):
    if len(series) <= n:
        return None
    a, b = series[-1 - n][1], series[-1][1]
    if kind == "yield":
        return (b - a) * 100
    return (b / a - 1) * 100 if a else None


def build_asset(spec: tuple, series, today: dt.date, live: tuple | None = None):
    """spec = row of config.ASSETS; live = (price, prev) from a fresher quote, optional."""
    aid, name, cls, page, src, sym, kind, unit = spec
    a = {"id": aid, "name": name, "cls": cls, "page": page, "kind": kind, "unit": unit, "ok": False}
    if not series or len(series) < 2:
        if live and live[0] and live[1]:
            series = [("prev", live[1]), (today.isoformat(), live[0])]
        else:
            return a
    series = [p for p in series if p[1] is not None]
    last_d, last = series[-1]
    prev = series[-2][1]
    if live and live[0] and live[1]:
        last, prev = live
        last_d = today.isoformat()
    d1 = (last - prev) * 100 if kind == "yield" else ((last / prev - 1) * 100 if prev else None)
    ch = _changes(series[-61:], kind)
    if len(ch) >= 20:
        vol = statistics.pstdev(ch[:-1]) or None
    else:
        vol = None
    vol = vol or C.DEFAULT_VOL_ASSET.get(aid) or C.DEFAULT_VOL.get(cls, 1.0)
    try:
        age = (today - dt.date.fromisoformat(last_d)).days
    except ValueError:
        age = 0
    a.update({
        "ok": True, "last": last, "prev": prev, "asof": last_d, "stale": age > 5,
        "d1": d1, "w1": _back(series, 5, kind), "m1": _back(series, 21, kind),
        "vol": vol, "z": (d1 / vol) if (d1 is not None and vol) else 0.0,
        "hist": [(d, v) for d, v in series[-70:] if d != "prev"],
    })
    a["zlabel"] = ("sharp" if abs(a["z"]) >= C.Z_SHARP else "notable" if abs(a["z"]) >= C.Z_NOTABLE else "quiet")
    return a


def public(a: dict) -> dict:
    """What the page and the writer see for one asset (display strings included)."""
    if not a.get("ok"):
        return {"id": a["id"], "name": a["name"], "ok": False}
    return {
        "id": a["id"], "ok": True, "name": a["name"], "class": a["cls"], "page": a["page"], "kind": a["kind"],
        "last": round(a["last"], 4), "lastText": fmt_level(a, a["last"]),
        "d1": round(a["d1"], 3) if a["d1"] is not None else None, "d1Text": fmt_move(a, a["d1"]),
        "w1Text": fmt_move(a, a["w1"]), "m1Text": fmt_move(a, a["m1"]),
        "z": round(a["z"], 2), "size": a["zlabel"], "asOf": a["asof"], "stale": a["stale"],
        "lagNote": lag_note(a["asof"]).strip(" ()") or None,
    }


# ------------------------------------------------------------------ regime

REGIMES = [
    ("risk_off", "Risk-off", {"us_eq": -1, "vix": 1, "gold": 1, "usdjpy": -1, "btc": -1, "us10y": -1}),
    ("risk_on", "Risk-on", {"us_eq": 1, "vix": -1, "usdjpy": 1, "btc": 1, "copper": 1}),
    ("inflation", "Inflation scare", {"brent": 1, "us2y": 1, "us10y": 1, "us_eq": -1, "natgas": 1}),
    ("growth", "Growth worries", {"us10y": -1, "copper": -1, "brent": -1, "us_eq": -1, "usdjpy": -1}),
    ("usd_up", "Strong dollar", {"eurusd": -1, "gbpusd": -1, "usdjpy": 1, "usdchf": 1, "gold": -1}),
    ("usd_down", "Weak dollar", {"eurusd": 1, "gbpusd": 1, "usdjpy": -1, "usdchf": -1, "gold": 1}),
]


def _fit(signs: dict, A: dict):
    xs = [max(-3.0, min(3.0, s * A[k]["z"])) for k, s in signs.items() if A.get(k, {}).get("ok") and not A[k]["stale"]]
    if len(xs) < max(2, int(0.6 * len(signs))):
        return None, 0
    return sum(xs) / len(xs), len(xs)


def regime(A: dict):
    best = None
    for rid, label, signs in REGIMES:
        score, n = _fit(signs, A)
        if score is None:
            continue
        members = sorted((k for k in signs if A.get(k, {}).get("ok")), key=lambda k: -signs[k] * A[k]["z"])
        cand = {"id": rid, "label": label, "score": round(score, 2), "members": members[:4]}
        if not best or score > best["score"]:
            best = cand
    zs = [abs(a["z"]) for a in A.values() if a.get("ok") and not a["stale"]]
    calm = (sum(zs) / len(zs)) if zs else 0
    if not best or best["score"] < 0.7:
        return {"id": "quiet" if calm < 0.6 else "mixed",
                "label": "Quiet session" if calm < 0.6 else "Mixed signals",
                "score": round(best["score"], 2) if best else 0, "members": [],
                "calm": round(calm, 2)}
    best["calm"] = round(calm, 2)
    return best


# ------------------------------------------------------------------ themes (news x markets)


def evaluate_theme(t: dict, news: dict | None, A: dict):
    signs = t["assets"]

    def side(mult):
        cons, contra, total = [], [], 0.0
        for k, s in signs.items():
            a = A.get(k)
            if not a or not a.get("ok") or a["stale"]:
                continue
            v = mult * s * a["z"]
            total += max(-3.0, min(3.0, v))
            if v >= C.CONFIRM_Z:
                cons.append(k)
            elif v <= -C.CONFIRM_Z:
                contra.append(k)
        return cons, contra, total

    orient = 1
    cons, contra, total = side(1)
    if t.get("two_way"):
        c2, k2, t2 = side(-1)
        if t2 > total:
            orient, cons, contra, total = -1, c2, k2, t2
    spike = (news or {}).get("spike") or 0
    hot = spike >= C.NEWS_SPIKE
    fits = len(cons) >= C.CONFIRM_ASSETS and len(cons) >= 2 * len(contra) + 1
    status = ("confirmed" if hot and fits else "news_only" if hot else
              "market_only" if len(cons) >= 3 and len(cons) > 2 * len(contra) else "quiet")
    score = (min(spike, 4.0) if hot else 1.0) * (total / max(1, len(signs)))
    direction = None
    if t.get("two_way"):
        direction = t.get("up") if orient == 1 else t.get("down")
    return {
        "id": t["id"], "label": t["label"], "channel": t.get("channel", ""), "status": status,
        "spike": round(spike, 2) if spike else None, "direction": direction,
        "consistent": cons, "against": contra, "score": round(score, 2),
        "headlines": ((news or {}).get("headlines") or [])[:4], "newsSource": (news or {}).get("source"),
    }


def tidy_themes(themes: list):
    """A pattern already explained by a confirmed theme is not credited to other themes."""
    explained = set()
    for t in themes:
        if t["status"] == "confirmed":
            explained |= set(t["consistent"])
    for t in themes:
        if t["status"] == "market_only" and set(t["consistent"]) <= explained:
            t["status"] = "quiet"
    return themes


# ------------------------------------------------------------------ lead story and charts


def pick_lead(themes: list, reg: dict, A: dict):
    conf = sorted((t for t in themes if t["status"] == "confirmed"), key=lambda t: -t["score"])
    if conf:
        return {"type": "theme", "id": conf[0]["id"], "label": conf[0]["label"], "assets": conf[0]["consistent"][:4]}
    if reg["id"] not in ("quiet", "mixed"):
        return {"type": "regime", "id": reg["id"], "label": reg["label"], "assets": reg["members"]}
    movers = sorted((a for a in A.values() if a.get("ok") and not a["stale"]), key=lambda a: -abs(a["z"]))
    if movers:
        return {"type": "mover", "id": movers[0]["id"], "label": movers[0]["name"],
                "assets": [m["id"] for m in movers[:3]]}
    return {"type": "none", "id": "", "label": "", "assets": []}


def chart_bars(A: dict):
    rows = []
    for k in C.CHART_BARS:
        a = A.get(k)
        if a and a.get("ok"):
            rows.append({"id": k, "name": a["name"], "class": a["cls"], "z": round(a["z"], 2),
                         "text": fmt_move(a, a["d1"]), "page": a["page"], "stale": a["stale"]})
    return rows


def chart_context(lead: dict, A: dict):
    """Chart 2: the two markets at the heart of the lead story, one month, rebased to 100."""
    # both lines share one unit: two prices (% change) or two yields (bp change)
    good = lambda k: A.get(k, {}).get("ok") and len(A[k]["hist"]) >= 10  # noqa: E731
    cand = [k for k in (lead.get("assets") or []) if good(k)]
    ids = cand[:1]
    if ids:
        kind = A[ids[0]]["kind"]
        cls = A[ids[0]]["cls"]
        more = [k for k in cand[1:] if A[k]["kind"] == kind and A[k]["cls"] != cls]
        more += [k for k in cand[1:] if A[k]["kind"] == kind and k not in more]
        fallback = (["us10y", "us2y", "us30y"] if kind == "yield"
                    else ["us_eq", "gold", "brent", "btc", "eurusd"])
        more += [k for k in fallback if good(k) and A[k]["kind"] == kind and k not in ids and k not in more]
        ids += more[:1]
    else:
        ids = [k for k in ("us_eq", "gold") if good(k)]
    out = []
    for k in ids:
        a = A[k]
        h = a["hist"][-23:]
        if a["kind"] == "yield":
            base = h[0][1]
            pts = [[d, round((v - base) * 100, 1)] for d, v in h]
            unit = "bp"
        else:
            base = h[0][1]
            pts = [[d, round((v / base - 1) * 100, 2)] for d, v in h]
            unit = "%"
        out.append({"id": k, "name": a["name"], "unit": unit, "page": a["page"], "points": pts})
    return {"title": "One month in context", "series": out,
            "note": "Change since the first day shown: % for prices, basis points for yields."}
