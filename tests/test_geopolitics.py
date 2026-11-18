"""GEOPOLITICAL RISK MONITOR — end-to-end run on simulated data (no network).
Checks the measures and that the published file matches the Framer component."""
import datetime as dt
import json
import math
import random

import pytest

from geopolitics import measure as M
from geopolitics import run as R
from geopolitics import sources as S
from geopolitics import writer as W


def _daily(seed, a, b, base, spike_at=None):
    rnd = random.Random(seed)
    out, d = [], a
    while d <= b:
        v = base * math.exp(rnd.gauss(0, 0.25))
        if spike_at and abs((d - spike_at).days) < 21:
            v *= 3
        out.append((d.isoformat(), v))
        d += dt.timedelta(days=1)
    return out


@pytest.fixture
def offline(monkeypatch, tmp_path):
    today = dt.date(2026, 11, 16)

    def gdelt(query, mode, a, b):
        seed = hash((query, mode)) % 10_000
        if mode == "timelinetone":
            return [(d, -3.0 + v) for d, v in _daily(seed, a, b, 0.5)]
        spike = today - dt.timedelta(days=14) if "Iran" in query else None
        return _daily(seed, a, b, 0.4, spike)

    def walk(seed, start, mu=0.0, vol=0.01, v0=100.0):
        rnd = random.Random(seed)
        out, d, v = [], start, v0
        while d <= today:
            if d.weekday() < 5:
                v *= math.exp(rnd.gauss(mu, vol))
                out.append((d.isoformat(), round(v, 4)))
            d += dt.timedelta(days=1)
        return out

    monkeypatch.setattr(S, "gdelt_timeline", gdelt)
    monkeypatch.setattr(S, "fred_series", lambda sid, start: walk(hash(sid) % 999, start, 0.0004 if sid == "DCOILBRENTEU" else 0.0))
    monkeypatch.setattr(S, "metals_series", lambda m: walk(hash(m) % 999, today - dt.timedelta(days=800)))
    monkeypatch.setattr(S, "headlines", lambda q, n=4: [{"title": "Sample headline", "url": "https://example.org", "source": "x"}])
    monkeypatch.setattr(W, "_call", lambda *a, **k: None)
    monkeypatch.setattr(R, "STORE", tmp_path / "attention.json")
    return dt.datetime(2026, 11, 16, 6, 20, tzinfo=R.NY)


def test_build_matches_component(offline, tmp_path):
    doc = R.build(offline)
    assert doc["week"] == {"year": 2026, "number": 47}
    assert doc["nextUpdate"].startswith("2026-11-23T11:15")
    assert len(doc["risks"]) == len(R.catalog())
    for r in doc["risks"]:
        assert set(["id", "label", "attention", "reaction", "levelAuto", "trend", "view", "assets"]) <= set(r)
        assert -3 <= r["attention"] <= 4 and -1 <= r["reaction"] <= 1
        assert r["levelAuto"] in ("high", "medium", "low")
        assert len(r["trend"]) == 12 and len(r["assets"]) == 3
        assert W.check_view(r["view"]) == [], (r["id"], r["view"])
        for a in r["assets"]:
            assert a["dir"] in (1, -1) and a["text"][0] in "+−" and a["z"] >= 0
    me = next(r for r in doc["risks"] if r["id"] == "middle_east")
    assert me["attention"] > 1          # simulated news spike two weeks ago
    g = doc["global"]
    assert g["series"][0][0] >= "2017-06-01" and g["series"][-1][0] == "2026-11-09"
    assert g["events"] and doc["calendar"] and all(e["date"] >= "2026-11-16" or e.get("end", "") >= "2026-11-16" for e in doc["calendar"])
    assert "automatic" not in json.dumps(doc).lower()
    out = tmp_path / "eb-geopolitics.json"
    R.write(out, doc)
    assert json.loads((tmp_path / "geopolitics" / "index.json").read_text())["weeks"] == ["2026-W47"]


def test_midweek_run_is_mondays_edition(offline):
    wed = offline + dt.timedelta(days=2, hours=3)
    doc = R.build(wed)
    assert doc["week"] == {"year": 2026, "number": 47} and doc["edition"] == "2026-11-16"
    assert doc["updated"].startswith("2026-11-16T11:15") and doc["nextUpdate"].startswith("2026-11-23")
    assert all(a["asOf"] <= "2026-11-15" for r in doc["risks"] for a in r["assets"])


def test_second_run_only_fetches_recent(offline, monkeypatch):
    R.build(offline)
    calls = []
    real = S.gdelt_timeline
    monkeypatch.setattr(S, "gdelt_timeline", lambda q, m, a, b: calls.append((a, b)) or real(q, m, a, b))
    R.build(offline)
    assert calls and all((b - a).days <= 60 for a, b in calls)


def test_override_wins(offline, monkeypatch, tmp_path):
    doc = R.build(offline)
    real = R._load
    monkeypatch.setattr(R, "_load", lambda p, d: {"risks": {"trade": {"level": "high", "view": "Hand-written view."}}}
                        if p.name == "override.json" else real(p, d))
    doc = R.apply_edits(doc, dt.date(2026, 11, 16))
    t = next(r for r in doc["risks"] if r["id"] == "trade")
    assert t["levelAuto"] == "high" and t["view"] == "Hand-written view."
    monkeypatch.setattr(R, "_load", real)
    doc = R.apply_edits(doc, dt.date(2026, 11, 16))
    t = next(r for r in doc["risks"] if r["id"] == "trade")
    assert t["view"] != "Hand-written view." and t["levelAuto"] == t["levelBase"]


def test_reaction_sign():
    up = {"move": 10.0, "dir": 1, "z": 2.0}
    down = {"move": -10.0, "dir": 1, "z": 2.0}
    assert M.reaction([up, up, up]) == 1.0
    assert M.reaction([down, down, down]) == -1.0
    assert M.reaction([up, None]) is None


def test_level_rule_matches_component():
    assert M.level(1.62, 0.62) == "high" and M.level(0.94, 0.21) == "medium" and M.level(0.38, -0.15) == "low"


def test_view_check():
    assert W.check_view("Tensions rose by 5% this week. Markets will rise.")
    assert not W.check_view("Shipping threats in the Gulf keep the conflict in the headlines. Oil and volatility are moving as they would if the risk were materialising.")
