"""GEOPOLITICAL RISK MONITOR — weekly update, Monday 06:15 New York.

    python -m geopolitics.run --out docs/eb-geopolitics.json            # normal run (skips outside Monday morning NY)
    python -m geopolitics.run --out docs/eb-geopolitics.json --force    # run now
    python -m geopolitics.run --out docs/eb-geopolitics.json --apply-edits
        # re-apply override.json, calendar.json and events.json to the published file (no data download)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

from . import config as C
from . import measure as M
from . import sources as S
from . import writer as W
from .sources import log

NY = ZoneInfo("America/New_York")
HERE = pathlib.Path(__file__).parent
STORE = HERE / "data" / "attention.json"


def _load(p: pathlib.Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def catalog() -> list[dict]:
    return [r for r in _load(HERE / "risks.json", {}).get("risks", []) if r.get("id") and r.get("query")]


# ------------------------------------------------------------------ attention (GDELT)


def update_attention(risks: list[dict], today: dt.date) -> dict:
    """Weekly coverage of each risk, kept in geopolitics/data/attention.json.
    The first run downloads the history since 2017 (two years per request); later runs
    only fetch the last six weeks."""
    store = _load(STORE, {"weeks": {}, "queries": {}})
    store.setdefault("weeks", {})
    store.setdefault("queries", {})
    first = dt.date.fromisoformat(C.HISTORY_START)
    first -= dt.timedelta(days=first.weekday())
    for r in risks:
        rid, q = r["id"], r["query"]
        weeks = store["weeks"].get(rid, {})
        if store["queries"].get(rid) != q:
            weeks = {}                                 # the query changed: rebuild the history
        chunks = []
        have = sorted(weeks)
        if not have or have[0] > (first + dt.timedelta(days=14)).isoformat():
            end_b = dt.date.fromisoformat(have[0]) - dt.timedelta(days=1) if have else today
            d = first
            while d <= end_b:
                e = min(d + dt.timedelta(days=7 * 104 - 1), end_b)
                chunks.append((d, e, "history"))
                d = e + dt.timedelta(days=1)
        rs = dt.date.fromisoformat(M.monday(today - dt.timedelta(days=C.REFRESH_DAYS)))
        chunks.append((rs, today, "recent"))
        log(f"News attention · {r['label']} ({len(chunks)} request{'s' if len(chunks) > 1 else ''}) …")
        for a, b, what in chunks:
            vol = S.gdelt_timeline(q, "timelinevol", a, b)
            if not vol:
                log(f"  no {what} data for {a} → {b}")
                continue
            tone = S.gdelt_timeline(q, "timelinetone", a, b) or []
            weeks.update({w: v for w, v in M.weekly(vol, tone).items()})
        store["weeks"][rid] = dict(sorted(weeks.items()))
        store["queries"][rid] = q
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(store, separators=(",", ":")))
    return store


# ------------------------------------------------------------------ build


def build(now_ny: dt.datetime) -> dict:
    today = now_ny.date()
    # The update belongs to the Monday of the current week: a run later in the week
    # (by hand) gives the same edition, based on data up to the Sunday before.
    edition = dt.date.fromisoformat(M.monday(today))
    cutoff = (edition - dt.timedelta(days=1)).isoformat()
    risks = catalog()
    store = update_attention(risks, today)
    last_week = (dt.date.fromisoformat(M.monday(today)) - dt.timedelta(days=7)).isoformat()

    z_all = {r["id"]: M.zscores(store["weeks"].get(r["id"], {}), last_week) for r in risks}

    log("Market prices (FRED, EB Metals) …")
    start = today - dt.timedelta(days=C.VOL_DAYS + C.MOVE_DAYS + 40)
    cache: dict[tuple, list | None] = {}

    def series(spec):
        k = (spec["src"], spec["id"])
        if k not in cache:
            cache[k] = S.fred_series(spec["id"], start) if spec["src"] == "fred" else S.metals_series(spec["id"])
        return cache[k]

    out = []
    for r in risks:
        z = [p for p in z_all[r["id"]] if p[0] <= last_week]
        if not z or z[-1][0] < (dt.date.fromisoformat(last_week) - dt.timedelta(days=14)).isoformat():
            log(f"  {r['id']}: no recent attention score, left out this week")
            continue
        assets = [M.asset_move(a, series(a), cutoff) for a in r.get("assets", [])]
        react = M.reaction(assets)
        if react is None:
            log(f"  {r['id']}: not enough price data, left out this week")
            continue
        att = z[-1][1]
        out.append({
            "id": r["id"],
            "label": r["label"],
            "attention": round(att, 2),
            "attentionChange": round(att - z[-2][1], 2) if len(z) > 1 else None,
            "reaction": react,
            "levelAuto": M.level(att, react),
            "trend": [round(v, 2) for _, v in z[-12:]],
            "assets": [a for a in assets if a],
            "headlines": S.headlines(r["query"]),
        })

    if len(out) < 3:
        raise SystemExit("Fewer than three risks could be measured: the published file is left unchanged.")

    log("Short views …")
    views = W.write_views(out)
    for r in out:
        r["view"] = r["viewBase"] = views.get(r["id"], "")
        r["levelBase"] = r["levelAuto"]
        r["headlines"] = [{"title": h.get("title", ""), "url": h.get("url", ""), "source": h.get("source", "")}
                          for h in r.get("headlines") or []][:3]

    g = M.global_series(z_all)
    g = [p for p in g if p[0] <= last_week]
    nxt = next_update(now_ny)
    wk = edition.isocalendar()
    published = dt.datetime(edition.year, edition.month, edition.day, C.PUBLISH_HOUR_NY,
                            C.PUBLISH_MINUTE_NY, tzinfo=NY).astimezone(dt.timezone.utc)
    doc = {
        "version": 1,
        "generated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "week": {"year": wk[0], "number": wk[1]},
        "updated": published.isoformat(),
        "edition": edition.isoformat(),
        "basedOn": last_week,
        "nextUpdate": nxt,
        "global": {
            "value": g[-1][1] if g else None,
            "change": round(g[-1][1] - g[-2][1], 2) if len(g) > 1 else None,
            "series": [[w, v] for w, v in g],
            "events": [],
        },
        "risks": out,
        "calendar": [],
        "sources": C.SOURCES,
    }
    return apply_edits(doc, today)


def next_update(now_ny: dt.datetime) -> str:
    d = now_ny.date() + dt.timedelta(days=1)
    while d.weekday() != C.PUBLISH_WEEKDAY:
        d += dt.timedelta(days=1)
    t = dt.datetime(d.year, d.month, d.day, C.PUBLISH_HOUR_NY, C.PUBLISH_MINUTE_NY, tzinfo=NY)
    return t.astimezone(dt.timezone.utc).isoformat()


# ------------------------------------------------------------------ editable files


def apply_edits(doc: dict, today: dt.date) -> dict:
    ov = _load(HERE / "override.json", {}).get("risks", {}) or {}
    for r in doc.get("risks", []):
        o = ov.get(r["id"]) or {}
        r.setdefault("levelBase", r.get("levelAuto") or M.level(r["attention"], r["reaction"]))
        r.setdefault("viewBase", r.get("view", ""))
        lv = str(o.get("level") or "").strip().lower()
        r["levelAuto"] = lv if lv in ("high", "medium", "low") else r["levelBase"]
        r["view"] = str(o.get("view") or "").strip() or r["viewBase"]
    cal = _load(HERE / "calendar.json", {}).get("events", []) or []
    keep = []
    for e in cal:
        d, en = str(e.get("date", ""))[:10], str(e.get("end") or "")[:10]
        if len(d) == 10 and e.get("title") and (en or d) >= today.isoformat():
            keep.append({k: v for k, v in {"date": d, "end": en or None, "title": e["title"],
                                           "region": e.get("region"), "risk": e.get("risk"),
                                           "note": e.get("note")}.items() if v})
    doc["calendar"] = sorted(keep, key=lambda e: e["date"])
    doc["global"]["events"] = [{"date": e["date"], "label": e["label"]}
                               for e in _load(HERE / "events.json", {}).get("events", []) if e.get("date") and e.get("label")]
    return doc


# ------------------------------------------------------------------ main


def write(out: pathlib.Path, doc: dict):
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    arch = out.parent / "geopolitics"
    arch.mkdir(exist_ok=True)
    name = f"{doc['week']['year']}-W{doc['week']['number']:02d}"
    (arch / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False))
    idx = sorted((p.stem for p in arch.glob("20*-W*.json")), reverse=True)
    (arch / "index.json").write_text(json.dumps({"weeks": idx}))
    print(f"Published {out} · week {name} · {len(doc['risks'])} risks")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/eb-geopolitics.json")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--apply-edits", action="store_true")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    now_ny = dt.datetime.now(NY)

    if a.apply_edits:
        if not out.exists():
            print("Nothing published yet.")
            return
        write(out, apply_edits(json.loads(out.read_text()), now_ny.date()))
        return

    force = a.force or os.environ.get("FORCE", "").lower() == "true"
    if not force:
        minutes = now_ny.hour * 60 + now_ny.minute
        start = C.PUBLISH_HOUR_NY * 60 + C.PUBLISH_MINUTE_NY - 5
        if now_ny.weekday() != C.PUBLISH_WEEKDAY or not start <= minutes < start + 360:
            print(f"{now_ny:%a %H:%M} in New York: outside the publishing window, nothing to do.")
            return
        if out.exists():
            try:
                w = json.loads(out.read_text())["week"]
                if (w["year"], w["number"]) == tuple(now_ny.date().isocalendar())[:2]:
                    print("This week's update is already published.")
                    return
            except Exception:  # noqa: BLE001
                pass
    write(out, build(now_ny))


if __name__ == "__main__":
    sys.exit(main())
