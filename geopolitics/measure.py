"""GEOPOLITICAL RISK MONITOR — the measures (pure functions, no network).

attention  weekly news coverage of each risk against its own five-year history
reaction   do the three assets tied to a risk move the way the risk would move them?
level      High / Medium / Low from both
"""
from __future__ import annotations

import datetime as dt
import math

from . import config as C


def monday(d: str | dt.date) -> str:
    if isinstance(d, str):
        d = dt.date.fromisoformat(d[:10])
    return (d - dt.timedelta(days=d.weekday())).isoformat()


# ------------------------------------------------------------------ attention


def weekly(vol: list[tuple[str, float]] | None, tone: list[tuple[str, float]] | None) -> dict[str, list[float]]:
    """Daily volume and tone -> {week (Monday): [mean volume, mean tone, days]}."""
    out: dict[str, list[float]] = {}
    tones = dict(tone or [])
    acc: dict[str, list] = {}
    for d, v in vol or []:
        a = acc.setdefault(monday(d), [0.0, 0.0, 0, 0])
        a[0] += v
        a[2] += 1
        if d in tones:
            a[1] += tones[d]
            a[3] += 1
    for w, (sv, st, nv, nt) in acc.items():
        out[w] = [round(sv / nv, 6), round(st / nt, 4) if nt else 0.0, nv]
    return out


def raw_score(vol: float, tone: float) -> float:
    """Coverage share, weighted up when the tone is negative."""
    return max(vol, 1e-6) * (1 + C.TONE_WEIGHT * max(0.0, -tone))


def zscores(weeks: dict[str, list[float]], complete_until: str) -> list[tuple[str, float]]:
    """z-score of log(raw score) of every complete week against the weeks before it
    (five years, exponentially weighted so recent years count more)."""
    keys = sorted(w for w, v in weeks.items() if w <= complete_until and v and v[2] >= 4)
    raw = [raw_score(weeks[w][0], weeks[w][1]) for w in keys]
    # two-week average, so one noisy week does not swing the score
    logs = [math.log((raw[i] + raw[i - 1]) / 2 if i else raw[i]) for i in range(len(raw))]
    out = []
    for i, w in enumerate(keys):
        lo = max(0, i - C.WINDOW_WEEKS)
        hist = logs[lo:i]
        if len(hist) < C.MIN_WEEKS:
            continue
        n = len(hist)
        wts = [1.0] * n if not C.HALF_LIFE_WEEKS else [0.5 ** ((n - k) / C.HALF_LIFE_WEEKS) for k in range(n)]
        sw = sum(wts)
        m = sum(x * a for x, a in zip(hist, wts)) / sw
        var = sum(a * (x - m) ** 2 for x, a in zip(hist, wts)) / sw
        sd = math.sqrt(var) if var > 1e-12 else 1e-6
        out.append((w, round(max(-3.0, min(4.0, (logs[i] - m) / sd)), 3)))
    return out


def global_series(per_risk: dict[str, list[tuple[str, float]]]) -> list[tuple[str, float]]:
    """Average attention of all risks, week by week (only weeks where most risks have a score)."""
    by_week: dict[str, list[float]] = {}
    for s in per_risk.values():
        for w, z in s:
            by_week.setdefault(w, []).append(z)
    need = max(1, math.ceil(len(per_risk) * 0.6))
    out, ema = [], None
    for w, v in sorted(by_week.items()):
        if len(v) < need:
            continue
        m = sum(v) / len(v)
        ema = m if ema is None else C.GLOBAL_SMOOTH * m + (1 - C.GLOBAL_SMOOTH) * ema
        out.append((w, round(ema, 3)))
    return out


# ------------------------------------------------------------------ market reaction


def _at(series, day: str):
    """Last value on or before a date."""
    v = None
    for d, x in series:
        if d > day:
            break
        v = x
    return v


def month_change(series, kind: str, end: str | None = None, days: int = C.MOVE_DAYS):
    if not series:
        return None
    end = end or series[-1][0]
    a = _at(series, (dt.date.fromisoformat(end) - dt.timedelta(days=days)).isoformat())
    b = _at(series, end)
    if a is None or b is None:
        return None
    if kind == "level":
        return (b - a) * 100          # percentage points -> basis points
    return (b / a - 1) * 100 if a else None


def usual_month_move(series, kind: str) -> float:
    """Standard deviation of one-month moves over the last two years (one sample per week)."""
    if series and len(series) > 60:
        last = dt.date.fromisoformat(series[-1][0])
        first = dt.date.fromisoformat(series[0][0]) + dt.timedelta(days=C.MOVE_DAYS)
        start = max(first, last - dt.timedelta(days=C.VOL_DAYS))
        moves, d = [], start
        while d <= last:
            m = month_change(series, kind, d.isoformat())
            if m is not None:
                moves.append(m)
            d += dt.timedelta(days=7)
        if len(moves) >= 20:
            mu = sum(moves) / len(moves)
            sd = math.sqrt(sum((x - mu) ** 2 for x in moves) / (len(moves) - 1))
            if sd > 1e-9:
                return sd
    return C.DEFAULT_MONTH_VOL[kind]


def prepare(series, invert: bool):
    if not series:
        return None
    if invert:
        return [(d, 1 / v) for d, v in series if v]
    return series


def asset_move(spec: dict, series, cutoff: str | None = None) -> dict | None:
    s = prepare(series, bool(spec.get("invert")))
    if s and cutoff:
        s = [p for p in s if p[0] <= cutoff] or None
    kind = spec.get("kind", "price")
    m = month_change(s, kind)
    if m is None:
        return None
    z = m / usual_month_move(s, kind)
    txt = (f"{m:+.0f} bp" if kind == "level" else f"{m:+.1f}%").replace("-", "−")
    return {"name": spec["name"], "dir": 1 if spec.get("dir", 1) > 0 else -1, "move": round(m, 2),
            "text": txt, "z": round(abs(z), 2), "page": spec.get("page", ""), "asOf": s[-1][0]}


def reaction(assets: list[dict]) -> float | None:
    """+1: the assets move as if the risk were happening, at full size; −1: the opposite way."""
    parts = []
    for a in assets:
        if a is None:
            continue
        sign = 1 if a["move"] > 0 else -1 if a["move"] < 0 else 0
        parts.append(sign * a["dir"] * min(a["z"] / C.FULL_Z, 1.0))
    if len(parts) < 2:
        return None
    return round(sum(parts) / len(parts), 2)


# ------------------------------------------------------------------ level


LEVELS = ["low", "medium", "high"]


def level(attention: float, react: float) -> str:
    """What the data alone say: attention and market reaction together."""
    s = 0.6 * attention + react
    return "high" if s >= C.LEVEL_HIGH else "medium" if s >= C.LEVEL_MEDIUM else "low"


def final_level(baseline: str | None, attention: float, react: float) -> str:
    """The structural level of the risk (risks.json, reviewed monthly) is the floor;
    strong attention and market reaction can only raise it."""
    sig = level(attention, react)
    base = baseline if baseline in LEVELS else "low"
    return max(base, sig, key=LEVELS.index)
