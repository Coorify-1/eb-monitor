"""Official lists of Shariah-compliant shares published by regulators and exchanges.

- Malaysia: Shariah Advisory Council of the Securities Commission (May and November)
- Indonesia: Otoritas Jasa Keuangan, Daftar Efek Syariah (May and November)
- United Arab Emirates: Dubai Financial Market, Fatwa and Shari'a Supervisory Board

Each list is read only when a new edition appears; the previous edition is kept to show
which shares entered or left the list.
"""
import datetime as dt
import io
import re

import requests

from . import config as C

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_s = requests.Session()


def _get(url, **kw):
    h = {"User-Agent": BROWSER, **kw.pop("headers", {})}
    for i in range(3):
        try:
            r = _s.get(url, headers=h, timeout=90, **kw)
            if r.status_code == 200:
                return r
        except requests.RequestException:
            pass
    return None


def pdf_lines(content):
    import pdfplumber
    lines = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for p in pdf.pages:
            lines += [l.strip() for l in (p.extract_text() or "").splitlines() if l.strip()]
    return lines


MONTHS = {m.lower(): i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)}
MONTHS.update({"mei": 5, "juni": 6, "juli": 7, "agustus": 8, "oktober": 10, "desember": 12, "januari": 1,
               "februari": 2, "maret": 3, "nopember": 11})


def parse_date(s):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", s or "")
    if not m or m.group(2).lower() not in MONTHS:
        return None
    return dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()


WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}


def words_to_int(w):
    w = w.lower().strip()
    if w.isdigit():
        return int(w)
    parts = re.split(r"[\s\-]+", w)
    n = 0
    for p in parts:
        if p in TENS:
            n += TENS[p]
        elif p in WORDS:
            n += WORDS[p]
        elif p == "hundred":
            n = max(1, n) * 100
        else:
            return None
    return n


def _diff(prev_names, names):
    a, b = set(prev_names or []), set(names)
    return sorted(b - a), sorted(a - b)


# ---------------------------------------------------------------- Malaysia

MY_SECTORS = [
    "CONSTRUCTION", "CONSUMER PRODUCTS & SERVICES", "CONSUMER PRODUCTS AND SERVICES", "ENERGY", "FINANCIAL SERVICES",
    "HEALTH CARE", "HEALTHCARE", "INDUSTRIAL PRODUCTS & SERVICES", "INDUSTRIAL PRODUCTS AND SERVICES", "PLANTATION",
    "PROPERTY", "REAL ESTATE INVESTMENT TRUSTS", "TECHNOLOGY", "TELECOMMUNICATIONS & MEDIA",
    "TELECOMMUNICATIONS AND MEDIA", "TRANSPORTATION & LOGISTICS", "TRANSPORTATION AND LOGISTICS", "UTILITIES",
    "SPECIAL PURPOSE ACQUISITION COMPANY", "CLOSED-END FUND", "EXCHANGE-TRADED FUND", "BUSINESS TRUST",
]
MY_ROW = re.compile(r"^(\d{1,4})\.?\s+([0-9]{4}[A-Z0-9]{0,3})\s+(.{2,90}?)\s*$")


def latest_sc_document():
    best = None
    for url in (C.SC_PAGE, "https://www.sc.com.my/development/icm/shariah-compliant-securities"):
        r = _get(url)
        if r is None:
            continue
        for m in re.finditer(r'"Page Description":"([^"]*Shariah[^"]*as at ([^"]+))"[^}]*?"Page Address":"([^"]+)"', r.text):
            d = parse_date(m.group(2))
            if d and (best is None or d > best[0]):
                best = (d, m.group(3), m.group(1))
    return best


def parse_sc(lines):
    names, sectors, sector = [], {}, None
    in_full = False
    for i, l in enumerate(lines):
        up = l.upper()
        if re.match(r"^(LIST OF|SENARAI) SHARIAH", up) and i > 20:
            in_full = True
        for s in MY_SECTORS:
            if up.startswith(s) and len(up) < len(s) + 25:
                sector = s.title().replace("And", "&")
                break
        m = MY_ROW.match(l)
        if m and sector:
            name = re.sub(r"\s+\d+$", "", m.group(3)).strip()
            names.append({"c": m.group(2), "n": name, "s": sector})
            sectors[sector] = sectors.get(sector, 0) + 1
    # the first tables list only the changes: keep the last occurrence of each code (full list comes last)
    seen, full = {}, []
    for x in names:
        seen[x["c"]] = x
    full = list(seen.values())
    sectors = {}
    for x in full:
        sectors[x["s"]] = sectors.get(x["s"], 0) + 1
    text = " ".join(lines[:80])
    added = removed = None
    m = re.search(r"([A-Za-z\-]+|\d+)\s+securities have been classified as Shariah-compliant", text)
    if m:
        added = words_to_int(m.group(1))
    m = re.search(r"while\s+([A-Za-z\-]+|\d+)\s+securities have been classified as Shariah non-compliant", text)
    if m:
        removed = words_to_int(m.group(1))
    total = None
    m = re.search(r"total of\s+([\d,]+)\s+Shariah-compliant securities", text)
    if m:
        total = int(m.group(1).replace(",", ""))
    pct = None
    m = re.search(r"([\d.]+)\s*(?:per cent|%)\s+of the total\s+([\d,]+)\s+listed", text)
    if m:
        pct = float(m.group(1))
    return full, sectors, added, removed, total, pct


def malaysia(cache, log=print):
    doc = latest_sc_document()
    if not doc:
        log("    Malaysia: list page not readable, keeping the last edition")
        return cache.get("MY")
    date, url, title = doc
    prev = cache.get("MY") or {}
    if prev.get("asOf") == date and prev.get("count"):
        return prev
    r = _get(url)
    if r is None or r.content[:4] != b"%PDF":
        log("    Malaysia: PDF not readable")
        return prev or None
    lines = pdf_lines(r.content)
    full, sectors, added, removed, total, pct = parse_sc(lines)
    log(f"    Malaysia {date}: {len(full)} securities parsed, {len(sectors)} sectors, +{added} -{removed}")
    if len(full) < 100:
        cache.setdefault("_debug", {})["MY"] = lines[:400]
        log("    Malaysia: too few rows parsed, keeping the last edition")
        return prev or None
    names = [x["n"] for x in full]
    a, rm = _diff(prev.get("_names"), names) if prev.get("_names") else ([], [])
    hist = [h for h in (prev.get("history") or []) if h[0] != date] + [[date, total or len(full)]]
    return {
        "code": "MY", "market": "Bursa Malaysia", "country": "Malaysia",
        "authority": "Shariah Advisory Council, Securities Commission Malaysia",
        "asOf": date, "url": url, "page": C.SC_PAGE, "title": title,
        "count": total or len(full), "share": pct,
        "addedCount": added if added is not None else (len(a) if prev.get("_names") else None),
        "removedCount": removed if removed is not None else (len(rm) if prev.get("_names") else None),
        "added": a[:60], "removed": rm[:60],
        "sectors": sorted([[k, v] for k, v in sectors.items()], key=lambda kv: -kv[1]),
        "history": sorted(hist)[-20:],
        "list": [[x["c"], x["n"], x["s"]] for x in full],
        "next": "Last Friday of May and November",
        "_names": names,
    }


# ---------------------------------------------------------------- Indonesia

ID_SECTOR = re.compile(r"^([A-K])\.\s+([A-Za-z ,&/-]{3,60})$")
ID_ROW = re.compile(r"^(\d{1,4})\s+([A-Z]{4})\s+(.{3,100}?)\s*$")
ID_SECTOR_EN = {
    "Energi": "Energy", "Barang Baku": "Basic materials", "Perindustrian": "Industrials",
    "Barang Konsumen Primer": "Consumer staples", "Barang Konsumen Non-Primer": "Consumer discretionary",
    "Kesehatan": "Health care", "Keuangan": "Financials", "Properti & Real Estat": "Property",
    "Properti dan Real Estat": "Property", "Teknologi": "Technology", "Infrastruktur": "Infrastructure",
    "Transportasi & Logistik": "Transport & logistics", "Transportasi dan Logistik": "Transport & logistics",
}


def latest_ojk_document():
    r = _get(C.OJK_PAGE)
    if r is None:
        return None
    pages = set(re.findall(r'/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/[^"\']*KEP(\d+)D04(\d{4})\.aspx', r.text))
    links = set(re.findall(r'(/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/[^"\']*KEP\d+D04\d{4}\.aspx)', r.text))
    if not links:
        return None
    def key(u):
        m = re.search(r"KEP(\d+)D04(\d{4})", u)
        return (int(m.group(2)), int(m.group(1)))
    page = "https://www.ojk.go.id" + max(links, key=key)
    p = _get(page)
    if p is None:
        return None
    pdfs = sorted(set(re.findall(r'(/id/kanal/syariah/[^"\']+\.pdf)', p.text)))
    lamp = [u for u in pdfs if "Lampiran" in requests.utils.unquote(u)]
    if not lamp:
        return None
    return page, "https://www.ojk.go.id" + lamp[0], key(page)


def parse_ojk(lines):
    rows, sector, issuer_section = [], None, False
    date = None
    for l in lines:
        if date is None and "Pada tanggal" in l:
            date = parse_date(l)
        if l.startswith("I. Saham yang Diterbitkan Emiten Syariah"):
            issuer_section, sector = True, "Sharia issuers"
            continue
        if l.startswith("II. Saham"):
            issuer_section = False
        m = ID_SECTOR.match(l)
        if m and not issuer_section:
            raw = m.group(2).strip()
            sector = ID_SECTOR_EN.get(raw, raw)
            continue
        m = ID_ROW.match(l)
        if m and sector:
            rows.append({"c": m.group(2), "n": m.group(3).strip(), "s": sector})
    seen = {}
    for x in rows:
        seen[x["c"]] = x
    return list(seen.values()), date


def indonesia(cache, log=print):
    doc = latest_ojk_document()
    prev = cache.get("ID") or {}
    if not doc:
        log("    Indonesia: list page not readable, keeping the last edition")
        return prev or None
    page, url, (year, num) = doc
    if prev.get("url") == url and prev.get("count"):
        return prev
    r = _get(url)
    if r is None or r.content[:4] != b"%PDF":
        log("    Indonesia: PDF not readable")
        return prev or None
    lines = pdf_lines(r.content)
    rows, date = parse_ojk(lines)
    log(f"    Indonesia KEP-{num}/{year}: {len(rows)} shares parsed, decree of {date}")
    if len(rows) < 100:
        cache.setdefault("_debug", {})["ID"] = lines[:300]
        return prev or None
    sectors = {}
    for x in rows:
        sectors[x["s"]] = sectors.get(x["s"], 0) + 1
    names = [x["n"] for x in rows]
    a, rm = _diff(prev.get("_names"), names) if prev.get("_names") else ([], [])
    as_of = date or f"{year}-06-01"
    hist = [h for h in (prev.get("history") or []) if h[0] != as_of] + [[as_of, len(rows)]]
    return {
        "code": "ID", "market": "Indonesia Stock Exchange", "country": "Indonesia",
        "authority": "Otoritas Jasa Keuangan (OJK), Daftar Efek Syariah",
        "asOf": as_of, "url": url, "page": page, "title": f"Daftar Efek Syariah KEP-{num}/D.04/{year}",
        "count": len(rows), "share": None,
        "addedCount": len(a) if prev.get("_names") else None, "removedCount": len(rm) if prev.get("_names") else None,
        "added": a[:60], "removed": rm[:60],
        "sectors": sorted([[k, v] for k, v in sectors.items()], key=lambda kv: -kv[1]),
        "history": sorted(hist)[-20:],
        "list": [[x["c"], x["n"], x["s"]] for x in rows],
        "next": "End of May and November",
        "_names": names,
    }


# ---------------------------------------------------------------- United Arab Emirates (Dubai)

def dubai(cache, log=print):
    prev = cache.get("AE") or {}
    try:
        r = _s.post(C.DFM_API, data="Command=shariahlisting&Language=en", timeout=60, headers={
            "User-Agent": BROWSER, "Origin": "https://www.dfm.ae", "Referer": "https://www.dfm.ae/",
            "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
        data = r.json() if r.status_code == 200 else None
    except Exception as e:
        log("    Dubai: request failed", e)
        data = None
    if not isinstance(data, list) or len(data) < 3:
        log(f"    Dubai: no list ({type(data).__name__}), keeping the last edition")
        cache.setdefault("_debug", {})["AE"] = str(data)[:3000]
        return prev or None
    head, rows = data[0], data[1:]
    cache.setdefault("_debug", {})["AE_sample"] = [head, rows[:3]]

    def field(row, *keys):
        if isinstance(row, dict):
            for k, v in row.items():
                if any(x in k.lower() for x in keys):
                    return v
        return None

    out = []
    for row in rows:
        if isinstance(row, dict):
            sym = field(row, "symbol", "code", "ticker")
            name = field(row, "name", "company")
            cls = field(row, "classif", "status", "compl", "sharia")
            mkt = field(row, "market", "exchange")
            sec = field(row, "sector")
        elif isinstance(row, list) and isinstance(head, list):
            d = dict(zip([str(h).lower() for h in head], row))
            sym = next((v for k, v in d.items() if "symbol" in k or "code" in k), None)
            name = next((v for k, v in d.items() if "name" in k or "company" in k), None)
            cls = next((v for k, v in d.items() if "class" in k or "status" in k or "compl" in k), None)
            mkt = next((v for k, v in d.items() if "market" in k), None)
            sec = next((v for k, v in d.items() if "sector" in k), None)
        else:
            continue
        if not name:
            continue
        st = None if cls is None else str(cls)
        ok = None if st is None else (not re.search(r"non|not|غير", st, re.I)
                                      and bool(re.search(r"compl|yes|true|^1$|متوافق", st, re.I)))
        out.append({"c": str(sym or ""), "n": str(name).strip(), "s": str(sec or mkt or "").strip(), "ok": ok})
    comp = [x for x in out if x["ok"] is not False]
    names = [x["n"] for x in comp]
    today = dt.date.today().isoformat()
    if prev.get("_names") and set(prev["_names"]) == set(names):
        prev["checked"] = today
        return prev
    a, rm = _diff(prev.get("_names"), names) if prev.get("_names") else ([], [])
    sectors = {}
    for x in comp:
        if x["s"]:
            sectors[x["s"]] = sectors.get(x["s"], 0) + 1
    hist = (prev.get("history") or []) + [[today, len(comp)]]
    log(f"    Dubai: {len(out)} rows, {len(comp)} compliant")
    return {
        "code": "AE", "market": "Dubai Financial Market and Nasdaq Dubai", "country": "United Arab Emirates",
        "authority": "DFM Fatwa and Shari'a Supervisory Board",
        "asOf": today, "checked": today, "url": C.DFM_PAGE, "page": C.DFM_PAGE, "title": "Shari'a Classification List",
        "count": len(comp), "total": len(out), "share": round(len(comp) / len(out) * 100, 1) if out else None,
        "addedCount": len(a) if prev.get("_names") else None, "removedCount": len(rm) if prev.get("_names") else None,
        "added": a[:60], "removed": rm[:60],
        "sectors": sorted([[k, v] for k, v in sectors.items()], key=lambda kv: -kv[1]),
        "history": hist[-20:],
        "list": [[x["c"], x["n"], x["s"]] for x in comp],
        "next": "Updated by DFM when companies publish results",
        "_names": names,
    }


def islamic_banks(lst):
    """Banks and financing companies on an official list (names that say Islamic, Syariah, Bank…)."""
    if not lst:
        return []
    pat = re.compile(r"islam|syariah|shariah|sharia|bank|takaful|muamalat|rajhi|financ", re.I)
    return [row[1] for row in lst.get("list", []) if pat.search(row[1])][:40]
