"""End-to-end run on simulated data (no network): checks the output matches the Framer component."""
import datetime as dt
import json
import os
import random

import numpy as np
import pandas as pd
import pytest

from engine import fundamentals as F
from engine import run as R
from engine import scoring as S
from engine import sources as SRC

N_BANK, N_COMP = 14, 40


def _company(i, bank):
    rnd = random.Random(i)
    return {
        "ticker": f"{'B' if bank else 'C'}{i:02d}",
        "cik": 1000 + i + (0 if bank else 500),
        "sic": 6021 if bank else rnd.choice([3570, 2834, 4911, 5331, 3711, 1311, 4813]),
        "price": rnd.uniform(20, 300),
        "drift": rnd.uniform(-0.0008, 0.0015),
        "shares": rnd.uniform(0.2e9, 3e9),
        "country": rnd.choice(["NY", "CA", "TX", "X0", "M5"]),
        "foreign": rnd.random() < 0.2,
        "rnd": rnd,
    }


CO = [_company(i, True) for i in range(N_BANK)] + [_company(i, False) for i in range(N_COMP)]


def _flow(v, end, years=4):
    rows = []
    e = dt.date.fromisoformat(end)
    for k in range(years):
        ee = e.replace(year=e.year - k)
        ss = ee.replace(year=ee.year - 1) + dt.timedelta(days=1)
        rows.append({"start": ss.isoformat(), "end": ee.isoformat(), "val": v * (0.92 ** k), "form": "10-K", "filed": (ee + dt.timedelta(days=50)).isoformat()})
    return rows


def _stock(v, end, years=4):
    e = dt.date.fromisoformat(end)
    return [{"end": e.replace(year=e.year - k).isoformat(), "val": v * (0.95 ** k), "form": "10-K", "filed": "2026-02-20"} for k in range(years)]


def _facts(c):
    r = c["rnd"]
    end = "2025-12-31"
    rev = r.uniform(10e9, 120e9)
    g = {}
    usd = lambda rows: {"units": {"USD": rows}}
    if c["sic"] == 6021:
        assets = r.uniform(200e9, 2000e9)
        g.update({
            "Assets": usd(_stock(assets, end)),
            "StockholdersEquity": usd(_stock(assets * r.uniform(0.07, 0.12), end)),
            "NetIncomeLoss": usd(_flow(assets * r.uniform(0.006, 0.014), end)),
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": usd(_flow(assets * 0.014, end)),
            "LoansAndLeasesReceivableNetReportedAmount": usd(_stock(assets * 0.55, end)),
            "Deposits": usd(_stock(assets * 0.7, end)),
            "FinancingReceivableExcludingAccruedInterestNonaccrual": usd(_stock(assets * 0.55 * r.uniform(0.003, 0.02), end)),
            "ProvisionForLoanLeaseAndOtherLosses": usd(_flow(assets * 0.003, end)),
            "NoninterestExpense": usd(_flow(assets * 0.025, end)),
            "InterestIncomeExpenseNet": usd(_flow(assets * 0.028, end)),
            "NoninterestIncome": usd(_flow(assets * 0.012, end)),
            "Goodwill": usd(_stock(assets * 0.01, end)),
            "BankingRegulationCommonEquityTierOneRiskBasedCapitalRatioActual": {"units": {"pure": _stock(r.uniform(0.10, 0.16), end)}},
        })
    else:
        g.update({
            "Revenues": usd(_flow(rev, end)),
            "GrossProfit": usd(_flow(rev * r.uniform(0.3, 0.6), end)),
            "OperatingIncomeLoss": usd(_flow(rev * r.uniform(0.05, 0.3), end)),
            "NetIncomeLoss": usd(_flow(rev * 0.1, end)),
            "NetCashProvidedByUsedInOperatingActivities": usd(_flow(rev * r.uniform(0.08, 0.3), end)),
            "PaymentsToAcquirePropertyPlantAndEquipment": usd(_flow(rev * 0.05, end)),
            "DepreciationDepletionAndAmortization": usd(_flow(rev * 0.04, end)),
            "Assets": usd(_stock(rev * 1.5, end)),
            "AssetsCurrent": usd(_stock(rev * 0.5, end)),
            "LiabilitiesCurrent": usd(_stock(rev * 0.35, end)),
            "Liabilities": usd(_stock(rev * 0.9, end)),
            "StockholdersEquity": usd(_stock(rev * 0.6, end)),
            "RetainedEarningsAccumulatedDeficit": usd(_stock(rev * 0.4, end)),
            "CashAndCashEquivalentsAtCarryingValue": usd(_stock(rev * 0.1, end)),
            "LongTermDebtNoncurrent": usd(_stock(rev * r.uniform(0.05, 0.6), end)),
        })
    tax = "ifrs-full" if c["foreign"] else "us-gaap"
    if c["foreign"]:
        ren = {"Revenues": "Revenue", "OperatingIncomeLoss": "ProfitLossFromOperatingActivities", "NetIncomeLoss": "ProfitLoss",
               "StockholdersEquity": "Equity", "NetCashProvidedByUsedInOperatingActivities": "CashFlowsFromUsedInOperatingActivities"}
        g = {ren.get(k, k): {"units": {("EUR" if u == "USD" else u): rows for u, rows in v["units"].items()}} for k, v in g.items()}
    facts = {"facts": {tax: g, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-01-31", "val": c["shares"], "form": "10-K", "filed": "2026-02-20"}]}}}}}
    return facts


class FakeMassive:
    calls = 0

    def grouped(self, day):
        d = dt.date.fromisoformat(day)
        n = (d - dt.date(2025, 1, 1)).days
        rows = [{"T": "SPY", "c": 500 * (1.0004 ** n), "v": 5e7}]
        for c in CO:
            rows.append({"T": c["ticker"], "c": c["price"] * ((1 + c["drift"]) ** n), "v": 2e6})
        return rows

    def splits_since(self, day):
        return []

    def details(self, t):
        c = next(x for x in CO if x["ticker"] == t)
        return {"market_cap": c["shares"] * c["price"] * 1.5}


class FakeSEC:
    def tickers(self):
        return [{"cik": c["cik"], "name": f"TEST {c['ticker']} CORP", "ticker": c["ticker"], "exchange": "NYSE"} for c in CO]

    def submissions(self, cik):
        c = next(x for x in CO if x["cik"] == cik)
        desc = {"NY": "NY", "CA": "CA", "TX": "TX", "X0": "UNITED KINGDOM", "M5": "SWITZERLAND"}[c["country"]]
        return {"sic": str(c["sic"]), "addresses": {"business": {"stateOrCountry": c["country"], "stateOrCountryDescription": desc, "city": "SOMEWHERE"}},
                "filings": {"recent": {"form": ["20-F"] if c["foreign"] else ["10-K"]}}}

    def facts(self, cik):
        return _facts(next(x for x in CO if x["cik"] == cik))


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(SRC, "Massive", FakeMassive)
    monkeypatch.setattr(SRC, "SEC", FakeSEC)
    monkeypatch.setattr(SRC, "wikidata_leadership", lambda ciks, by_ticker=False: {} if by_ticker else {1000: {"itemLabel": "Test Bank Zero", "ceoLabel": "Jane Doe", "ceoStart": "2020-03-01T00:00:00Z", "ceoDesc": "banker", "emp": 1234, "web": "https://example.com", "cc": "US", "hqLabel": "Boston"}})
    monkeypatch.setattr(SRC, "person_photo", lambda *a, **k: None)
    monkeypatch.setattr(SRC, "commons_logo", lambda *a, **k: None)
    monkeypatch.setattr(SRC, "site_icon", lambda *a, **k: (b"\x89PNG\r\n\x1a\n" + b"0" * 400, "png"))
    monkeypatch.setattr(SRC, "press_page", lambda *a, **k: "https://example.com/newsroom")
    monkeypatch.setattr(SRC, "fetch_photo", lambda *a, **k: b"\xff\xd8\xff" + b"0" * 2000)
    monkeypatch.setattr(SRC, "fred", lambda s: [("2026-01-01", 1.0), ("2026-01-02", 1.1)] * 40)
    monkeypatch.setattr(SRC, "fx_per_usd", lambda: {"USD": 1.0, "EUR": 0.9})
    monkeypatch.setattr(R.time, "sleep", lambda *_: None)
    monkeypatch.setattr(R.C, "MIN_MARKET_CAP_USD", 1e9)
    return tmp_path


def test_full_run(fake, monkeypatch):
    out = fake / "docs" / "eb-monitor.json"
    monkeypatch.setattr("sys.argv", ["run", "--out", str(out), "--cache", str(fake / "cache")])
    R.main()
    j = json.load(open(out))
    assert len(j["banking"]) == 5 and len(j["company"]) == 5
    for kind in ("banking", "company"):
        ranks = [i["rank"] for i in j[kind]]
        assert ranks == [1, 2, 3, 4, 5]
        scores = [i["score"] for i in j[kind]]
        assert scores == sorted(scores, reverse=True)
        for it in j[kind]:
            for k in ("name", "ticker", "country", "score", "pillars", "why", "headline", "metrics", "risks"):
                assert k in it, (k, it)
            assert 0 <= it["score"] <= 100
            assert all(0 <= p["score"] <= 100 for p in it["pillars"])
            assert len(it["metrics"]) >= 4
            assert "prevRank" not in it  # first week
        # max 2 per country
        cc = pd.Series([i["country"] for i in j[kind]]).value_counts()
        assert cc.max() <= 2
    comp_sectors = pd.Series([i["sector"] for i in j["company"]]).value_counts()
    assert comp_sectors.max() <= 2
    assert j["regime"]["label"] in ("Risk-on", "Neutral", "Risk-off")
    print(json.dumps(j["banking"][0], indent=1)[:1500])
    print(json.dumps(j["company"][0], indent=1)[:1500])

    # second week: picks keep their place, prevRank appears, cache grows only a few days
    monkeypatch.setattr(R, "last_finished_day", lambda now: dt.date.fromisoformat(j["asOf"]) + dt.timedelta(days=7))
    R.main()
    j2 = json.load(open(out))
    assert all("prevRank" in i for i in j2["banking"])
    same = {i["ticker"] for i in j["banking"]} & {i["ticker"] for i in j2["banking"]}
    assert len(same) >= 4


def test_extract_prefers_latest_concept():
    facts = {"facts": {"us-gaap": {
        "SalesRevenueNet": {"units": {"USD": _flow(5e9, "2019-12-31")}},
        "Revenues": {"units": {"USD": _flow(9e9, "2025-12-31")}},
    }}}
    f = F.extract(facts)
    assert f["t"]["revenue"] == pytest.approx(9e9)
    assert f["p"]["revenue"] == pytest.approx(9e9 * 0.92)


def test_pick_stability_and_caps():
    d = pd.DataFrame({
        "ticker": list("ABCDEFGHIJKL"),
        "score": [90, 89, 88, 87, 86, 85, 84, 83, 82, 81, 80, 79],
        "country": ["US", "US", "US", "GB", "GB", "GB", "JP", "JP", "FR", "DE", "CH", "CA"],
        "sector": ["x"] * 12,
    })
    p = S.pick(d, {"I": 1}, sector_cap=False)  # I is 9th: kept (top 10)
    assert "I" in set(p.ticker)
    assert p.country.value_counts().max() <= 2
    p2 = S.pick(d, {"L": 1}, sector_cap=False)  # L is 12th: replaced
    assert "L" not in set(p2.ticker)


def test_verified_ceo_form4_and_annual_report():
    class R:
        def __init__(self, t):
            self.text = t

    form4 = "<reportingOwner><rptOwnerName>FRASER JANE NIND</rptOwnerName><officerTitle>Chief Executive Officer</officerTitle></reportingOwner>"
    other = "<reportingOwner><rptOwnerName>SMITH JOHN</rptOwnerName><officerTitle>CFO</officerTitle></reportingOwner>"

    class Sec:
        def _get(self, url, ok404=True):
            return R(other if "a1" in url else form4)

    sub = {"filings": {"recent": {"form": ["4", "4", "10-K"], "accessionNumber": ["a1", "a2", "k1"],
                                  "primaryDocument": ["xsl/f.xml", "xsl/g.xml", "k.htm"], "filingDate": ["2026-11-01", "2026-10-01", "2026-02-20"]}}}
    text = "/s/ Jane Fraser Jane Fraser Chief Executive Officer"
    name, src, wd = SRC.verified_ceo(Sec(), 1, sub, False, "Jane Fraser", text, {"form": "10-K", "date": "2026-02-20"})
    assert name == "Jane Fraser" and wd and "Form 4" in src
    # stale Wikidata name is replaced, its portrait must not be kept
    name, src, wd = SRC.verified_ceo(Sec(), 1, sub, False, "Michael Corbat", text, {"form": "10-K", "date": "2026-02-20"})
    assert name == "Jane Fraser" and not wd
    # foreign filer: the annual report decides
    t20 = "Georges Elhedery, Group Chief Executive, said ... Georges Elhedery, Group Chief Executive"
    name, src, wd = SRC.verified_ceo(Sec(), 1, sub, True, "Noel Quinn", t20, {"form": "20-F", "date": "2026-02-25"})
    assert name == "Georges Elhedery" and not wd
    name, src, wd = SRC.verified_ceo(Sec(), 1, sub, True, None, "nothing here", {"form": "20-F", "date": "2026-02-25"})
    assert name is None


def test_next_update_skips_a_week_already_published():
    ny = R.NY
    at = lambda *a: dt.datetime(*a, tzinfo=ny)
    friday = dt.date(2026, 11, 13)
    # published by hand on Sunday with Friday's data: Monday's run will skip, so announce the Monday after
    assert R.next_update(friday, at(2026, 11, 15, 19, 0)) == at(2026, 11, 23, 7, 0)
    # normal Monday run after 7:00
    assert R.next_update(friday, at(2026, 11, 16, 8, 0)) == at(2026, 11, 23, 7, 0)
    # manual run on a Tuesday with Monday's data
    assert R.next_update(dt.date(2026, 11, 16), at(2026, 11, 17, 10, 0)) == at(2026, 11, 23, 7, 0)
    # across the US clock change (Nov 1, 2026): still 7:00 New York
    assert R.next_update(dt.date(2026, 10, 23), at(2026, 10, 31, 12, 0)) == at(2026, 11, 2, 7, 0)
    assert R.next_update(dt.date(2026, 10, 30), at(2026, 10, 31, 12, 0)) == at(2026, 11, 9, 7, 0)


def test_press_kit_photo_from_overrides(fake, monkeypatch):
    """Method 2: the editor adds the official portrait from the company's press page."""
    ov = {f"B{i:02d}": {"ceo": {"name": "Ann Lee", "photo": f"https://bank{i}.example/press/ann-lee.jpg"}} for i in range(N_BANK)}
    ov["B01"]["ceo"]["photoCredit"] = "Test Bank One, media centre"
    ov.update({f"C{i:02d}": {"ceo": {"name": "Bob Roe"}} for i in range(N_COMP)})
    monkeypatch.setattr(R, "_overrides", lambda: ov)
    out = fake / "docs" / "eb-monitor.json"
    monkeypatch.setattr("sys.argv", ["run", "--out", str(out), "--cache", str(fake / "cache")])
    R.main()
    j = json.load(open(out))
    for it in j["banking"]:
        c = it["ceo"]
        assert c["name"] == "Ann Lee"
        assert c["photo"].startswith("https://cdn.jsdelivr.net/gh/") and "/docs/ceo/" + it["ticker"] + "-" in c["photo"]
        assert (fake / "docs" / "ceo" / c["photo"].rsplit("/", 1)[-1]).exists()
        assert c["photoCredit"] == ("Test Bank One, media centre" if it["ticker"] == "B01" else it["name"] + ", press kit")
    for it in j["company"]:
        assert it["ceo"]["name"] == "Bob Roe" and "photo" not in it["ceo"]
    check = open(fake / "docs" / "CHECK.md").read()
    assert "Photo officielle de l'espace presse" in check
    assert "dans l'[espace presse](https://example.com/newsroom)" in check

    # a new photo link replaces the old file (new name, so no cache shows the old portrait)
    t = j["banking"][0]["ticker"]
    old = j["banking"][0]["ceo"]["photo"].rsplit("/", 1)[-1]
    new = R.official_photo(t, "https://new.example/portrait.jpg", str(out)).rsplit("/", 1)[-1]
    files = [f for f in os.listdir(fake / "docs" / "ceo") if f.startswith(t + "-")]
    assert files == [new] and new != old


def test_press_page_finds_newsroom(monkeypatch):
    html = ('<a href="https://facebook.com/x">Media</a><a href="/careers">Careers</a>'
            '<a href="/about/media">Media</a><a href="https://www.acme.com/en/newsroom">Newsroom</a>'
            '<a href="https://other.com/press">Press</a>')

    class Resp:
        def __init__(self, url, text="", status=200):
            self.url, self.text, self.status_code = url, text, status

    monkeypatch.setattr(SRC._s, "get", lambda url, **k: Resp("https://www.acme.com/", html) if url.rstrip("/").endswith("acme.com") else Resp(url, "", 404))
    assert SRC.press_page("acme.com") == "https://www.acme.com/en/newsroom"
    # no link on the home page: try the usual addresses
    monkeypatch.setattr(SRC._s, "get", lambda url, **k: Resp(url, "<html>ok</html>") if url.endswith("/media") or url.rstrip("/").endswith("acme.com") else Resp(url, "", 404))
    assert SRC.press_page("https://acme.com") == "https://acme.com/media"
