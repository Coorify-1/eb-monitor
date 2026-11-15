"""Data sources. Every source is free and public; Massive needs a free API key."""
import csv
import io
import os
import re
import time
from html import unescape

import requests

UA = os.environ.get("SEC_CONTACT", "").strip() or "Economic Bearings research"
MASSIVE_KEY = os.environ.get("MASSIVE_API_KEY", "").strip()
MASSIVE = "https://api.massive.com"

_s = requests.Session()


def get(url, *, params=None, headers=None, tries=4, timeout=60, ok404=False):
    h = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
    h.update(headers or {})
    for i in range(tries):
        try:
            r = _s.get(url, params=params, headers=h, timeout=timeout)
        except requests.RequestException as e:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))
            continue
        if r.status_code == 404 and ok404:
            return None
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", 0) or 0) or 15 * (i + 1)
            time.sleep(min(wait, 90))
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"Too many retries: {url}")


# ---------------- Massive (prices) ----------------

class Massive:
    """Free Stocks Basic plan: 5 calls per minute, end-of-day data."""

    def __init__(self, key=MASSIVE_KEY, per_minute=5):
        if not key:
            raise RuntimeError("MASSIVE_API_KEY is missing (GitHub secret).")
        self.key = key
        self.gap = 60.0 / per_minute + 0.6
        self.last = 0.0
        self.calls = 0

    def call(self, path, params=None):
        wait = self.gap - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        p = dict(params or {})
        p["apiKey"] = self.key
        try:
            r = get(MASSIVE + path, params=p, ok404=True)
        finally:
            self.last = time.time()
            self.calls += 1
        return r.json() if r is not None else None

    def grouped(self, day):
        """One close per US stock for one trading day (adjusted)."""
        j = self.call(f"/v2/aggs/grouped/locale/us/market/stocks/{day}", {"adjusted": "true"})
        return (j or {}).get("results") or []

    def splits_since(self, day):
        out, path, params = [], "/v3/reference/splits", {"execution_date.gte": day, "limit": 1000}
        for _ in range(5):
            j = self.call(path, params)
            if not j:
                break
            out += j.get("results") or []
            nxt = j.get("next_url")
            if not nxt:
                break
            path, params = nxt.replace(MASSIVE, "").replace("https://api.polygon.io", ""), {}
        return out

    def details(self, ticker):
        j = self.call(f"/v3/reference/tickers/{ticker}")
        return (j or {}).get("results") or {}


# ---------------- SEC EDGAR ----------------

class SEC:
    """SEC asks for at most 10 requests per second and a contact in the User-Agent."""

    def __init__(self):
        self.last = 0.0

    def _get(self, url, ok404=True):
        wait = 0.12 - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        try:
            return get(url, ok404=ok404, timeout=120)
        finally:
            self.last = time.time()

    def tickers(self):
        r = self._get("https://www.sec.gov/files/company_tickers_exchange.json", ok404=False)
        j = r.json()
        f = j["fields"]
        return [dict(zip(f, row)) for row in j["data"]]

    def submissions(self, cik):
        r = self._get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        return r.json() if r is not None else None

    def facts(self, cik):
        r = self._get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
        return r.json() if r is not None else None


# ---------------- Wikidata + Commons (leadership, photos) ----------------

WD = "https://query.wikidata.org/sparql"

LEAD_QUERY = """
SELECT ?cik ?itemLabel ?ceoLabel ?ceoDesc ?ceoStart ?ceoImg ?chairLabel ?emp ?empDate ?web ?hqLabel ?cc WHERE {
  VALUES ?cik { %s }
  ?item wdt:P5531 ?cik .
  OPTIONAL {
    ?item p:P169 ?st . ?st ps:P169 ?ceo .
    FILTER NOT EXISTS { ?st pq:P582 ?stEnd }
    OPTIONAL { ?st pq:P580 ?ceoStart }
    OPTIONAL { ?ceo wdt:P18 ?ceoImg }
    OPTIONAL { ?ceo schema:description ?ceoDesc FILTER(LANG(?ceoDesc) = "en") }
  }
  OPTIONAL { ?item p:P488 ?cs . ?cs ps:P488 ?chair . FILTER NOT EXISTS { ?cs pq:P582 ?csEnd } }
  OPTIONAL { ?item p:P1128 ?es . ?es ps:P1128 ?emp . OPTIONAL { ?es pq:P585 ?empDate } }
  OPTIONAL { ?item wdt:P856 ?web }
  OPTIONAL { ?item wdt:P159 ?hq }
  OPTIONAL { ?item wdt:P17 ?c . ?c wdt:P297 ?cc }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def wikidata_leadership(ciks):
    """Leadership facts by CIK from Wikidata (CC0)."""
    out = {}
    ciks = [int(c) for c in ciks]
    for i in range(0, len(ciks), 60):
        part = ciks[i : i + 60]
        vals = " ".join(f'"{c}" "{c:010d}"' for c in part)
        try:
            r = get(
                WD,
                params={"query": LEAD_QUERY % vals, "format": "json"},
                headers={"Accept": "application/sparql-results+json"},
                timeout=120,
            )
        except Exception as e:  # leadership is optional
            print("  wikidata batch failed:", e)
            continue
        for b in r.json()["results"]["bindings"]:
            v = {k: x["value"] for k, x in b.items()}
            cik = int(v["cik"])
            d = out.setdefault(cik, {"emp": None, "empDate": ""})
            for k in ("itemLabel", "ceoLabel", "ceoDesc", "ceoStart", "ceoImg", "chairLabel", "web", "hqLabel", "cc"):
                if v.get(k) and not d.get(k):
                    d[k] = v[k]
            if v.get("emp"):
                date = v.get("empDate", "")
                if d["emp"] is None or date > d["empDate"]:
                    try:
                        d["emp"] = int(float(v["emp"]))
                        d["empDate"] = date
                    except ValueError:
                        pass
        time.sleep(1)
    return out


FREE_LICENSE = re.compile(r"^(CC0|CC BY(-SA)? [0-9.]+|Public domain|PD\b)", re.I)


def commons_photo(file_url, width=160):
    """Thumbnail + credit for a Wikimedia Commons file, only if freely licensed."""
    name = file_url.rsplit("/", 1)[-1]
    name = requests.utils.unquote(name)
    try:
        r = get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query", "titles": "File:" + name, "prop": "imageinfo",
                "iiprop": "url|extmetadata", "iiurlwidth": width, "format": "json",
            },
            timeout=60,
        )
    except Exception:
        return None
    pages = (r.json().get("query") or {}).get("pages") or {}
    for p in pages.values():
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        if not FREE_LICENSE.search(lic.strip()):
            return None
        artist = re.sub(r"<[^>]+>", "", unescape((meta.get("Artist") or {}).get("value", ""))).strip()
        artist = re.sub(r"\s+", " ", artist)[:60] or "Wikimedia Commons"
        return {"photo": info.get("thumburl") or info.get("url"), "photoCredit": f"{artist}, {lic.strip()}, via Wikimedia Commons"}
    return None


# ---------------- FRED (market regime) + FX ----------------

def fred(series_id):
    """Daily values from FRED's public CSV download (no key)."""
    r = get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id}, timeout=60)
    rows = list(csv.reader(io.StringIO(r.text)))[1:]
    out = []
    for d, v in rows:
        try:
            out.append((d, float(v)))
        except ValueError:
            pass
    return out


def fx_per_usd():
    """Units of each currency per 1 USD (ECB reference rates via Frankfurter)."""
    try:
        r = get("https://api.frankfurter.dev/v1/latest", params={"base": "USD"}, timeout=30)
        rates = r.json().get("rates") or {}
        rates["USD"] = 1.0
        return rates
    except Exception as e:
        print("  fx failed:", e)
        return {"USD": 1.0}
