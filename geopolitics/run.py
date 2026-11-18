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
import time
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


def update_attention(risks: list[dict], today: dt.date, budget_min: float = C.GDELT_BUDGET_MIN) -> dict:
    """Weekly coverage of each risk, kept in geopolitics/data/attention.json.
    First the recent weeks of every risk (two years for a new risk, enough to publish);
    then older history back to 2017, newest first, within a time budget. What is missing
    is fetched on the next runs (a daily run does only that)."""
    t0 = time.time()
    store = _load(STORE, {"weeks": {}, "queries": {}})
    store.setdefault("weeks", {})
    store.setdefault("queries", {})
    first = dt.date.fromisoformat(C.HISTORY_START)

    def save():
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(store, separators=(",", ":")))

    def fetch(r, a, b, what):
        vol = S.gdelt_timeline(r["query"], "timelinevol", a, b)
        if not vol:
            log(f"  {r['id']}: no {what} data for {a} → {b} (will retry next run)")
            return False
        tone = S.gdelt_timeline(r["query"], "timelinetone", a, b) if C.TONE_WEIGHT else []
        store["weeks"].setdefault(r["id"], {}).update(M.weekly(vol, tone))
        store["weeks"][r["id"]] = dict(sorted(store["weeks"][r["id"]].items()))
        save()
        return True

    for r in risks:
        if store["queries"].get(r["id"]) != r["query"]:
            store["weeks"][r["id"]] = {}               # new risk or changed query: start again
            store["queries"][r["id"]] = r["query"]
    log("News attention: recent weeks …")
    for r in risks:
        have = store["weeks"].get(r["id"]) or {}
        days = C.REFRESH_DAYS if len(have) >= C.MIN_WEEKS else C.FIRST_DAYS
        fetch(r, dt.date.fromisoformat(M.monday(today - dt.timedelta(days=days))), today, "recent")

    log("News attention: older history …")
    while time.time() - t0 < budget_min * 60:
        todo = []
        for r in risks:
            have = sorted(store["weeks"].get(r["id"]) or {})
            if have and have[0] > (first + dt.timedelta(days=10)).isoformat():
                e = dt.date.fromisoformat(have[0]) - dt.timedelta(days=1)
                todo.append((r, max(first, e - dt.timedelta(days=7 * 104 - 1)), e))
        if not todo:
            log("  history complete since " + C.HISTORY_START)
            break
        progress = False
        for r, a, b in todo:
            if time.time() - t0 >= budget_min * 60:
                break
            progress |= fetch(r, a, b, "history")
        if not progress:
            break
    else:
        log("  time budget used: older history continues on the next run")
    save()
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
            "levelAuto": M.final_level(r.get("level"), att, react),
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
        r.setdefault("levelBase", r.get("levelAuto") or M.final_level(None, r["attention"], r["reaction"]))
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


def refresh_global(doc: dict, store: dict) -> dict:
    """Recompute the global attention line of a published edition from the stored history
    (the risks' own figures and texts are left as published)."""
    upto = doc.get("basedOn")
    if not upto:
        return doc
    z_all = {r["id"]: M.zscores(store["weeks"].get(r["id"], {}), upto) for r in catalog()}
    g = [p for p in M.global_series(z_all) if p[0] <= upto]
    if g:
        doc["global"]["series"] = [[w, v] for w, v in g]
        doc["global"]["value"] = g[-1][1]
        doc["global"]["change"] = round(g[-1][1] - g[-2][1], 2) if len(g) > 1 else None
    return doc


# ------------------------------------------------------------------ main


def write(out: pathlib.Path, doc: dict, archive: bool = True):
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
    ap.add_argument("--history", action="store_true", help="only fill older news history, publish nothing")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    now_ny = dt.datetime.now(NY)

    if a.history:
        store = update_attention(catalog(), now_ny.date(), budget_min=float(os.environ.get("BUDGET_MIN", 80)))
        if out.exists():          # longer history: redraw this edition's global attention line
            write(out, refresh_global(json.loads(out.read_text()), store), archive=True)
        return

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
