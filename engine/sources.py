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
SELECT ?cik ?item ?itemLabel ?ceoLabel ?ceoDesc ?ceoStart ?ceoEnd ?ceoImg ?chairLabel ?chairEnd ?emp ?empDate ?web ?hqLabel ?cc WHERE {
  VALUES ?cik { %s }
  ?item wdt:P5531 ?cik .
  OPTIONAL {
    ?item p:P169 ?st . ?st ps:P169 ?ceo .
    OPTIONAL { ?st pq:P580 ?ceoStart }
    OPTIONAL { ?st pq:P582 ?ceoEnd }
    OPTIONAL { ?ceo wdt:P18 ?ceoImg }
    OPTIONAL { ?ceo schema:description ?ceoDesc FILTER(LANG(?ceoDesc) = "en") }
  }
  OPTIONAL { ?item p:P488 ?cs . ?cs ps:P488 ?chair . OPTIONAL { ?cs pq:P582 ?chairEnd } }
  OPTIONAL { ?item p:P1128 ?es . ?es ps:P1128 ?emp . OPTIONAL { ?es pq:P585 ?empDate } }
  OPTIONAL { ?item wdt:P856 ?web }
  OPTIONAL { ?item wdt:P159 ?hq }
  OPTIONAL { ?item wdt:P17 ?c . ?c wdt:P297 ?cc }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


def _pick_web(urls):
    """Main website: no country sub-site, shortest domain."""
    from urllib.parse import urlparse

    def key(u):
        host = urlparse(u).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        return (host.count(".") > 1, not host.endswith((".com", ".org", ".net")), len(host), len(u))

    urls = sorted(set(urls), key=key)
    return urls[0] if urls else None


def wikidata_leadership(ciks):
    """Leadership facts by CIK from Wikidata (CC0). The current CEO is the one with the latest start and no end."""
    raw = {}
    ciks = [int(c) for c in ciks]
    for i in range(0, len(ciks), 40):
        part = ciks[i : i + 40]
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
            raw.setdefault(int(v["cik"]), []).append(v)
        time.sleep(1)
    out = {}
    for cik, rows in raw.items():
        d = {"emp": None, "empDate": ""}
        labels = {r["itemLabel"] for r in rows if r.get("itemLabel")}
        d["itemLabel"] = sorted(labels, key=len)[0] if labels else None
        items = {r["item"].rsplit("/", 1)[-1] for r in rows if r.get("item")}
        d["qid"] = sorted(items)[0] if len(items) == 1 else None
        # CEO: open statements, latest start wins; an ended or older mandate never wins over a newer one
        ceos = {}
        for r in rows:
            if r.get("ceoLabel"):
                c = ceos.setdefault(r["ceoLabel"], {"start": "", "end": "", "img": None, "desc": None})
                c["start"] = max(c["start"], r.get("ceoStart", ""))
                c["end"] = max(c["end"], r.get("ceoEnd", ""))
                c["img"] = c["img"] or r.get("ceoImg")
                c["desc"] = c["desc"] or r.get("ceoDesc")
        latest = max((c["start"] for c in ceos.values()), default="")
        cur = [(n, c) for n, c in ceos.items() if not c["end"] and c["start"] == latest]
        if len(cur) == 1:
            n, c = cur[0]
            d.update({"ceoLabel": n, "ceoStart": c["start"], "ceoImg": c["img"], "ceoDesc": c["desc"]})
        chairs = {r["chairLabel"] for r in rows if r.get("chairLabel") and not r.get("chairEnd")}
        if len(chairs) == 1:
            d["chairLabel"] = chairs.pop()
        for r in rows:
            if r.get("emp"):
                date = r.get("empDate", "")
                if d["emp"] is None or date > d["empDate"]:
                    try:
                        d["emp"], d["empDate"] = int(float(r["emp"])), date
                    except ValueError:
                        pass
        webs = [r["web"] for r in rows if r.get("web")]
        d["web"] = _pick_web(webs)
        hqs = {r["hqLabel"] for r in rows if r.get("hqLabel")}
        if len(hqs) == 1:
            d["hqLabel"] = hqs.pop()
        ccs = {r["cc"] for r in rows if r.get("cc")}
        if len(ccs) == 1:
            d["cc"] = ccs.pop()
        out[cik] = d
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


# ---------------- Leadership checked against official SEC documents ----------------

CEO_TITLE = re.compile(
    r"^\s*((executive\s+)?chair(man|woman|person)?(\s+of\s+the\s+board)?\s*(and|&|,)\s*)?"
    r"(president\s*(and|&|,)\s*)?(group\s+)?(chief\s+executive(\s+officer)?|ceo)"
    r"(\s*(and|&|,)\s*(president|chair(man|woman|person)?(\s+of\s+the\s+board)?|director))*\s*$",
    re.I,
)
NAME_BEFORE_CEO = re.compile(
    r"([A-Z][a-zA-Z'\-]+(?:\s+(?:van|von|de|der|den|da|di|du|le|la)?\s*(?!Group\b|Chief\b|Executive\b|Our\b|The\b)[A-Z][a-zA-Z'\-]+){1,3})\s*,?\s+"
    r"(?:our\s+|the\s+)?(?:Group\s+)?(?:Chief\s+Executive(?:\s+Officer)?|CEO)\b"
)
TITLE_BEFORE_NAME = re.compile(
    r"\b(?:Group\s+)?(?:Chief\s+Executive(?:\s+Officer)?|CEO)\s*[,:\-–]?\s+"
    r"((?!Officer\b|Committee\b|Group\b|Board\b|and\b|of\b)[A-Z][a-zA-Z'\-]+(?:\s+(?:van|von|de|der|den|da|di|du|le|la)?\s*[A-Z][a-zA-Z'\-]+){1,2})\b"
)
SIGNATURE_CEO = re.compile(
    r"/s/\s*([A-Za-z.'\- ]{3,90}?)\s*,?\s*"
    r"(?:Chair(?:man|woman)?(?: of the Board)?,?\s*(?:and\s+)?)?(?:President,?\s*(?:and\s+)?)?Chief Executive Officer"
)


def _sig_name(seg):
    """'John J. Christmann IV John J. Christmann IV' -> 'John Christmann'."""
    words = [w for w in seg.split() if not re.fullmatch(r"[A-Za-z]\.?|Jr\.?|Sr\.?|I+|IV|V|VI", w, re.I)]
    h = len(words) // 2
    if h and len(words) % 2 == 0 and [w.lower() for w in words[:h]] == [w.lower() for w in words[h:]]:
        words = words[:h]
    words = words[:3]
    return " ".join(w if any(c.islower() for c in w) else w.title() for w in words) if len(words) >= 2 else None


def _recent(sub, forms, n):
    r = (sub.get("filings") or {}).get("recent") or {}
    out = []
    for f, acc, doc, date in zip(r.get("form", []), r.get("accessionNumber", []), r.get("primaryDocument", []), r.get("filingDate", [])):
        if f in forms:
            out.append((f, acc, doc, date))
            if len(out) >= n:
                break
    return out


def _doc_url(cik, acc, doc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{doc}"


def _text(html):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", unescape(t))


def _form4_name(raw):
    """'FRASER JANE NIND' (last, first, middle) -> 'Jane Fraser'."""
    parts = [p for p in re.split(r"[\s,]+", raw.strip()) if p]
    if len(parts) < 2:
        return raw.title()
    return f"{parts[1].title()} {parts[0].title()}"


def ceo_from_form4(sec, cik, sub, max_docs=25):
    """Latest insider filing (Form 4) whose official title is CEO. Domestic companies only."""
    for f, acc, doc, date in _recent(sub, {"4", "4/A"}, max_docs):
        raw_doc = doc.split("/")[-1]  # drop the xsl viewer folder
        r = sec._get(_doc_url(cik, acc, raw_doc))
        if r is None:
            continue
        x = r.text
        for owner in re.findall(r"(?s)<reportingOwner>(.*?)</reportingOwner>", x):
            title = re.search(r"<officerTitle>\s*(.*?)\s*</officerTitle>", owner, re.S)
            name = re.search(r"<rptOwnerName>\s*(.*?)\s*</rptOwnerName>", owner, re.S)
            if title and name and CEO_TITLE.match(unescape(title.group(1))):
                return {"raw": unescape(name.group(1)), "name": _form4_name(unescape(name.group(1))), "date": date}
    return None


def annual_report_text(sec, cik, sub, deep=False):
    """Text of the latest annual report. deep=True also reads the biggest attached documents
    (foreign companies often file the annual report itself as an exhibit)."""
    rows = _recent(sub, {"10-K", "20-F", "40-F", "10-K/A", "20-F/A", "40-F/A"}, 1)
    if not rows:
        return "", None
    f, acc, doc, date = rows[0]
    r = sec._get(_doc_url(cik, acc, doc))
    parts = [_text(r.text)] if r is not None else []
    if deep:
        idx = sec._get(_doc_url(cik, acc, "index.json"))
        try:
            items = idx.json()["directory"]["item"] if idx is not None else []
        except Exception:
            items = []
        htm = [i for i in items if i.get("name", "").lower().endswith((".htm", ".html")) and i.get("name") != doc]
        htm.sort(key=lambda i: -int(i.get("size") or 0))
        for i in htm[:3]:
            x = sec._get(_doc_url(cik, acc, i["name"]))
            if x is not None:
                parts.append(_text(x.text))
    return " ".join(parts), {"form": f, "date": date, "url": _doc_url(cik, acc, doc)}


def _last(name):
    return re.sub(r"[^a-z]", "", (name or "").split()[-1].lower()) if name else ""


FORMER = re.compile(r"\b(former|previous|retired|outgoing|predecessor|until|stepped down|succeeded)\b", re.I)


def named_as_ceo(text, name, min_hits=3):
    """True if the annual report repeatedly names this person as Chief Executive (not as a former one)."""
    if not text or not name:
        return False
    last = re.escape(name.split()[-1])
    pat = re.compile(rf"{last}.{{0,120}}?(Chief Executive|\bCEO\b)|(Chief Executive|\bCEO\b).{{0,120}}?{last}", re.I)
    hits = 0
    for m in pat.finditer(text):
        around = text[max(0, m.start() - 60): m.end()]
        if not FORMER.search(around):
            hits += 1
    return hits >= min_hits


def ceo_from_text(text):
    """Most cited name in front of 'Chief Executive' in the annual report."""
    if not text:
        return None
    counts = {}
    for m in NAME_BEFORE_CEO.finditer(text):
        if FORMER.search(text[max(0, m.start() - 40): m.end()]):
            continue
        n = m.group(1).strip()
        if len(n.split()) < 2 or n.split()[0].lower() in {"the", "our", "former", "interim", "deputy", "and", "group"}:
            continue
        counts[n] = counts.get(n, 0) + 1
    for m in TITLE_BEFORE_NAME.finditer(text):
        if FORMER.search(text[max(0, m.start() - 40): m.end()]):
            continue
        n = m.group(1).strip()
        if len(n.split()) >= 2 and n.split()[0].lower() not in {"the", "our", "former", "interim", "deputy"}:
            counts[n] = counts.get(n, 0) + 1
    for m in SIGNATURE_CEO.finditer(text):
        n = _sig_name(m.group(1))
        if n:
            counts[n] = counts.get(n, 0) + 3
    if not counts:
        return None
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0] if best[1] >= 2 else None


def named_near(text, name, word):
    if not text or not name:
        return False
    last = re.escape(name.split()[-1])
    return bool(re.search(rf"{last}.{{0,100}}{word}|{word}.{{0,100}}{last}", text, re.I))


def verified_ceo(sec, cik, sub, foreign, wd_name, text, doc):
    """Returns (name, source, wikidata_matches) or (None, reason, False). Nothing unconfirmed is returned."""
    doc = doc or {"form": "annual report", "date": ""}
    if not foreign:
        f4 = ceo_from_form4(sec, cik, sub)
        if f4:
            if wd_name and _last(wd_name) == _last(f4["raw"].split()[0]):
                return wd_name, f"SEC Form 4 ({f4['date']})", True
            sig = ceo_from_text(text)
            if sig and _last(sig) == _last(f4["raw"].split()[0]):
                return sig, f"SEC Form 4 ({f4['date']})", False
            return f4["name"], f"SEC Form 4 ({f4['date']})", False
    found = ceo_from_text(text)
    if found:
        same = bool(wd_name and _last(wd_name) == _last(found))
        return (wd_name if same else found), f"{doc['form']} annual report ({doc['date']})", same
    if wd_name and named_as_ceo(text, wd_name):
        return wd_name, f"{doc['form']} annual report ({doc['date']})", True
    return None, "not confirmed by an official filing", False
