"""THE ANALYST — data adapters.

One small function per Economic Bearings source. Each returns plain Python data and
never raises: a source that does not answer simply returns None, and the analysis
works with what is left. Series are lists of (YYYY-MM-DD, value), oldest first.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from . import config as C

LOG: list[str] = []


def log(*a):
    msg = " ".join(str(x) for x in a)
    LOG.append(msg)
    print(msg, flush=True)


def get(url: str, params: dict | None = None, tries: int = 3, timeout: int = 30, as_json=True, headers=None):
    h = {"User-Agent": C.UA, "Accept": "application/json" if as_json else "*/*"}
    h.update(headers or {})
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=h, timeout=timeout)
            if r.status_code == 200:
                return r.json() if as_json else r.text
            log(f"  {url[:70]} -> HTTP {r.status_code}")
            if r.status_code in (400, 401, 403, 404):
                return None
        except Exception as e:  # noqa: BLE001
            log(f"  {url[:70]} failed: {str(e)[:100]}")
        time.sleep(3 + 4 * i)
    return None


def _num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _clean(series):
    out = {}
    for d, v in series:
        v = _num(v)
        if d and v is not None:
            out[str(d)[:10]] = v
    return sorted(out.items())


# ------------------------------------------------------------------ Financial Markets Worker (FRED…)

def market_history(symbol: str, rng: str = "3M"):
    j = get(f"{C.MARKET_WORKER}/history", {"symbol": symbol, "range": rng})
    vals = (j or {}).get("values") or []
    s = _clean((x.get("datetime"), x.get("close")) for x in vals if isinstance(x, dict))
    if symbol.startswith("FRED:"):  # holidays are forward-filled: drop exact repeats
        s = [p for i, p in enumerate(s) if i == 0 or p[1] != s[i - 1][1]]
    return s or None


def market_quotes(symbols: list[str]):
    j = get(f"{C.MARKET_WORKER}/quotes", {"symbols": ",".join(symbols)})
    return (j or {}).get("data") or {}


# ------------------------------------------------------------------ Hard Assets (Metals Worker)

def metals_now():
    return get(C.METALS_WORKER + "/")


def metals_history(metal: str, rng: str = "6mo"):
    j = get(C.METALS_WORKER + "/", {"history": metal, "range": rng})
    pts = (j or {}).get("points") or []
    s = _clean((p[0], p[1]) for p in pts if isinstance(p, list) and len(p) >= 2)
    return s or None


# ------------------------------------------------------------------ Crypto & Currencies

def fx_history(days: int = 140):
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    j = get(f"{C.FRANKFURTER}/{start}..", {"base": "USD", "symbols": "EUR,JPY,GBP,CHF,CNY"})
    rates = (j or {}).get("rates") or {}
    if not rates:
        return None
    out = {k: [] for k in ("eurusd", "usdjpy", "gbpusd", "usdchf", "usdcny")}
    for d in sorted(rates):
        r = rates[d]
        if r.get("EUR"):
            out["eurusd"].append((d, 1 / r["EUR"]))
        if r.get("GBP"):
            out["gbpusd"].append((d, 1 / r["GBP"]))
        if r.get("JPY"):
            out["usdjpy"].append((d, r["JPY"]))
        if r.get("CHF"):
            out["usdchf"].append((d, r["CHF"]))
        if r.get("CNY"):
            out["usdcny"].append((d, r["CNY"]))
    return out


def crypto_history(coin: str, days: int = 120):
    j = get(f"{C.COINGECKO}/coins/{coin}/market_chart",
            {"vs_currency": "usd", "days": days, "interval": "daily"})
    pts = (j or {}).get("prices") or []
    s = _clean((dt.datetime.fromtimestamp(p[0] / 1000, dt.timezone.utc).date().isoformat(), p[1])
               for p in pts if isinstance(p, list) and len(p) >= 2)
    return s or None


def crypto_global():
    j = get(f"{C.COINGECKO}/global", tries=1)
    d = (j or {}).get("data") or {}
    if not d:
        return None
    return {"mcapChg24h": _num(d.get("market_cap_change_percentage_24h_usd")),
            "btcDominance": _num((d.get("market_cap_percentage") or {}).get("btc"))}


# ------------------------------------------------------------------ EB engines already published

def eb_json(url: str):
    return get(url, timeout=60)


# ------------------------------------------------------------------ Estate Index Worker

def estate_world():
    j = get(C.ESTATE_WORKER.rstrip("/") + "/world")
    rows = (j or {}).get("countries") or []
    out = []
    for r in rows:
        a = _num(r.get("annual"))
        if r.get("name") and a is not None:
            out.append({"name": r["name"], "annual": a, "period": r.get("period") or "", "src": r.get("src") or ""})
    return out or None


# ------------------------------------------------------------------ Energy Terminal (CEII open API)

def _walk(o, depth=0):
    if depth > 6:
        return
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v, depth + 1)
    elif isinstance(o, list):
        for v in o[:400]:
            yield from _walk(v, depth + 1)


def _first(d: dict, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/124 Safari/537.36")


def ceii_items(name: str, limit: int = 12):
    """Generic reader for CEII lists (news, events): title + link + date."""
    j = get(f"{C.CEII_API}/{name}.json", timeout=40, tries=2,
            headers={"User-Agent": BROWSER, "Referer": "https://terminal.centreforenergy.org/"})
    if not j:
        return None
    out, seen = [], set()
    for d in _walk(j):
        title = _first(d, ("title", "headline", "name", "event", "label"))
        if not isinstance(title, str) or len(title) < 8:
            continue
        url = _first(d, ("url", "link", "href", "source_url"))
        date = _first(d, ("date", "published", "publishedAt", "pubDate", "time", "start", "datetime", "when"))
        src = _first(d, ("source", "domain", "publisher", "site"))
        if isinstance(src, dict):
            src = src.get("name")
        key = title.strip().lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title.strip()[:180], "url": url if isinstance(url, str) and url.startswith("http") else "",
                    "date": str(date)[:25] if date else "", "source": str(src or "")[:60]})
        if len(out) >= limit:
            break
    return out or None


# ------------------------------------------------------------------ Geopolitics: GDELT, Google News fallback

_NEWS_MODE: str | None = None


def gdelt_volume(query: str, days: int = 21):
    """Daily share of world news coverage matching the query (GDELT DOC 2.0)."""
    end = dt.datetime.utcnow()
    start = end - dt.timedelta(days=days)
    j = get("https://api.gdeltproject.org/api/v2/doc/doc", {
        "query": f"{query} sourcelang:english", "mode": "timelinevol", "format": "json",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"), "enddatetime": end.strftime("%Y%m%d%H%M%S"),
        "timelinesmooth": 0}, tries=2, timeout=40)
    data = ((j or {}).get("timeline") or [{}])[0].get("data") or []
    daily: dict[str, list[float]] = {}
    for x in data:
        d = str(x.get("date", ""))[:8]
        v = _num(x.get("value"))
        if len(d) == 8 and v is not None:
            daily.setdefault(f"{d[:4]}-{d[4:6]}-{d[6:]}", []).append(v)
    s = [(d, sum(v) / len(v)) for d, v in sorted(daily.items())]
    return s if len(s) >= 7 else None


def gdelt_articles(query: str, n: int = 4, span: str = "36h"):
    j = get("https://api.gdeltproject.org/api/v2/doc/doc", {
        "query": f"{query} sourcelang:english", "mode": "ArtList", "maxrecords": 40,
        "format": "json", "timespan": span, "sort": "HybridRel"}, tries=2, timeout=40)
    out, seen = [], set()
    for a in (j or {}).get("articles") or []:
        t = (a.get("title") or "").strip()
        k = t.lower()[:60]
        if not t or k in seen:
            continue
        seen.add(k)
        sd = a.get("seendate") or ""
        out.append({"title": t[:180], "url": a.get("url") or "", "source": (a.get("domain") or "").replace("www.", ""),
                    "date": f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}" if len(sd) >= 8 else ""})
        if len(out) >= n:
            break
    return out


def _rss(query: str, window: bool = True):
    txt = get("https://news.google.com/rss/search",
              {"q": f"{query} when:14d" if window else query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
              tries=2, as_json=False, headers={"Accept": "application/rss+xml"})
    if not txt:
        return None
    try:
        root = ET.fromstring(txt)
    except ET.ParseError:
        return None
    items = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and t.endswith(" - " + src):
            t = t[: -len(src) - 3]
        try:
            d = email.utils.parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except Exception:  # noqa: BLE001
            d = ""
        items.append({"title": t[:180], "url": it.findtext("link") or "", "source": src, "date": d})
    return items


def _rss_count(query: str, after: dt.date, before: dt.date):
    items = _rss(f"{query} after:{after.isoformat()} before:{before.isoformat()}", window=False)
    return items


def theme_news(theme: dict, today: dt.date):
    """News intensity of a theme: coverage of the last 2 days vs. the 12 days before.

    Google News is used (GDELT rate-limits GitHub's machines). Each window is asked
    separately so the busy recent days do not crowd out the baseline."""
    q = theme["query"]
    recent = _rss_count(q, today - dt.timedelta(days=2), today + dt.timedelta(days=1))
    time.sleep(2)
    base = _rss_count(q, today - dt.timedelta(days=14), today - dt.timedelta(days=2))
    time.sleep(2)
    if recent is None or base is None:
        return None
    r_day = len(recent) / 2
    b_day = len(base) / 12
    if len(recent) < 4:
        spike = 1.0  # too little coverage to call anything
    else:
        spike = r_day / max(b_day, 1.0)
    spike = min(spike, 6.0)
    heads = sorted([i for i in recent if i["title"]], key=lambda x: x["date"], reverse=True)[:4]
    return {"spike": round(spike, 2), "source": "Google News", "headlines": heads,
            "counts": [len(recent), len(base)]}


# ------------------------------------------------------------------ helpers
def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def qs(d: dict) -> str:
    return urllib.parse.urlencode(d)


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))
