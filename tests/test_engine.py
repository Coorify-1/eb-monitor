"""End-to-end run on simulated data (no network): checks the output matches the Framer component."""
import datetime as dt
import json
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
    monkeypatch.setattr(SRC, "wikidata_leadership", lambda ciks: {1000: {"itemLabel": "Test Bank Zero", "ceoLabel": "Jane Doe", "ceoStart": "2020-03-01T00:00:00Z", "ceoDesc": "banker", "emp": 1234, "web": "https://example.com", "cc": "US", "hqLabel": "Boston"}})
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
