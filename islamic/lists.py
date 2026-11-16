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

MY_SECTORS = ["INDUSTRIAL PRODUCTS AND SERVICES", "CONSUMER PRODUCTS AND SERVICES", "TECHNOLOGY", "PROPERTY", "CONSTRUCTION",
    "ENERGY", "PLANTATION", "TRANSPORTATION AND LOGISTICS", "HEALTH CARE", "HEALTHCARE", "TELECOMMUNICATIONS AND MEDIA",
    "UTILITIES", "FINANCIAL SERVICES", "REAL ESTATE INVESTMENT TRUSTS", "CLOSED-END FUND", "EXCHANGE-TRADED FUND",
    "BUSINESS TRUST", "SPECIAL PURPOSE ACQUISITION COMPANY"]
ROW = re.compile(r"^(\d{1,4})\.\s+(\d{4,5}[A-Z0-9]{0,2})\s+(.+)$")
TAIL = re.compile(r"(Bhd|Berhad|Ltd|Limited|Plc|Trust|REIT|Fund|ETF|Corporation|Group|Holdings)\.?\)?$", re.I)

def undouble(l):
    def w(x):
        return x[::2] if len(x) >= 2 and len(x) % 2 == 0 and all(x[i] == x[i + 1] for i in range(0, len(x), 2)) else x
    return " ".join(w(x) for x in l.split(" "))


def columns(page):
    w = page.width
    nums = [x["x0"] for x in page.extract_words() if re.fullmatch(r"\d{1,4}\.", x["text"])]
    right = [x for x in nums if x > w * 0.4]
    split = (min(right) - 3) if right else w / 2
    return [page.crop((0, 0, split, page.height)).extract_text() or "", page.crop((split, 0, w, page.height)).extract_text() or ""]

def parse_full(pdf):
    rows, sector, market, started, hdr = [], None, "Main", False, []
    for page in pdf.pages:
        full = page.extract_text() or ""
        if "LIST OF SHARIAH-COMPLIANT SECURITIES –" in full or "LIST OF SHARIAH-COMPLIANT SECURITIES -" in full:
            started = True
        if not started:
            continue
        if re.search(r"Islamic exchange-traded funds|Islamic real estate investment trusts", full) and not ROW.search(full.split("\n")[5] if len(full.split("\n"))>5 else ""):
            pass
        for col in columns(page):
            for l in col.split("\n"):
                l = l.strip()
                if not l:
                    continue
                m = ROW.match(l)
                if m:
                    hdr = []
                    if sector:
                        rows.append({"c": m.group(2), "n": m.group(3).strip(), "s": sector, "m": market})
                    continue
                l = undouble(l).replace("*", "").strip()
                up = l.upper()
                if l == up and re.search(r"[A-Z]", l):
                    if re.fullmatch(r"(MAIN|ACE|LEAP) MARKET", up):
                        market = {"MAIN": "Main", "ACE": "ACE", "LEAP": "LEAP"}[up.split()[0]]; hdr = []; continue
                    hdr.append(up)
                    for k in (1, 2, 3):
                        j = " ".join(hdr[-k:])
                        if j in MY_SECTORS:
                            sector = j.capitalize().replace("Health care", "Healthcare"); hdr = []
                            break
                    continue
                if rows and not TAIL.search(rows[-1]["n"]) and len(l) < 40 and not re.match(r"(No\.|Bil\.|Shariah|List of|Senarai)", l):
                    rows[-1]["n"] += " " + l
    return rows

def parse_table3(lines):
    out, cur, on = [], None, False
    for l in lines:
        if re.match(r"^Table 3", l): on = True; continue
        if not on: continue
        if l.upper() in MY_SECTORS or l.upper().replace(" ", "") == "HEALTHCARE": cur = l
        m = re.search(r"(\d+|Nil)\s+([\d,]+|Nil)\s+(\d+)$", l)
        if l.startswith("Total"): cur = "Total"
        if m and cur:
            out.append([cur, 0 if m.group(1) == "Nil" else int(m.group(1)), 0 if m.group(2)=="Nil" else int(m.group(2).replace(",", "")), int(m.group(3))])
            if cur == "Total": break
            cur = None
    return out


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


def sc_intro(lines):
    text = " ".join(lines[:80])
    added = removed = None
    m = re.search(r"([A-Za-z\-]+|\d+)\s+securities have been classified as Shariah-compliant", text)
    if m:
        added = words_to_int(m.group(1))
    m = re.search(r"while\s+([A-Za-z\-]+|\d+)\s+securities have been classified as Shariah non-compliant", text)
    if m:
        removed = words_to_int(m.group(1))
    return added, removed


def malaysia(cache, log=print):
    doc = latest_sc_document()
    if not doc:
        log("    Malaysia: list page not readable, keeping the last edition")
        return cache.get("MY")
    date, url, title = doc
    prev = cache.get("MY") or {}
    if prev.get("asOf") == date and prev.get("count") and prev.get("v") == 2:
        return prev
    r = _get(url)
    if r is None or r.content[:4] != b"%PDF":
        log("    Malaysia: PDF not readable")
        return prev or None
    import pdfplumber
    pdf = pdfplumber.open(io.BytesIO(r.content))
    lines = [l for pg in pdf.pages for l in (pg.extract_text() or "").split("\n")]
    full = parse_full(pdf)
    t3 = parse_table3(lines)
    added, removed = sc_intro(lines)
    tot = next((x for x in t3 if x[0] == "Total"), None)
    total, pct, listed = (tot[1], tot[3], tot[2]) if tot else (None, None, None)
    sectors = {x[0]: x[1] for x in t3 if x[0] != "Total"}
    if not sectors:
        for x in full:
            sectors[x["s"]] = sectors.get(x["s"], 0) + 1
    log(f"    Malaysia {date}: {len(full)} securities parsed, {len(sectors)} sectors, total {total}, +{added} -{removed}")
    if len(full) < 100:
        cache.setdefault("_debug", {})["MY"] = lines[:400]
        log("    Malaysia: too few rows parsed, keeping the last edition")
        return prev or None
    names = [x["n"] for x in full]
    a, rm = _diff(prev.get("_names"), names) if prev.get("_names") else ([], [])
    hist = [h for h in (prev.get("history") or []) if h[0] != date] + [[date, total or len(full)]]
    return {
        "v": 2, "code": "MY", "market": "Bursa Malaysia", "country": "Malaysia",
        "authority": "Shariah Advisory Council, Securities Commission Malaysia",
        "asOf": date, "url": url, "page": C.SC_PAGE, "title": title,
        "count": total or len(full), "share": pct, "listed": listed,
        "sectorShare": [[x[0], x[1], x[2], x[3]] for x in t3 if x[0] != "Total"],
        "markets": {m: sum(1 for x in full if x["m"] == m) for m in ("Main", "ACE", "LEAP")},
        "addedCount": added if added is not None else (len(a) if prev.get("_names") else None),
        "removedCount": removed if removed is not None else (len(rm) if prev.get("_names") else None),
        "added": a[:60], "removed": rm[:60],
        "sectors": sorted([[k, v] for k, v in sectors.items()], key=lambda kv: -kv[1]),
        "history": sorted(hist)[-20:],
        "list": [[x["c"], x["n"], x["s"], x["m"]] for x in full],
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

def _dfm(body):
    r = _s.post(C.DFM_API, data=body, timeout=60, headers={
        "User-Agent": BROWSER, "Origin": "https://www.dfm.ae", "Referer": "https://www.dfm.ae/",
        "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"})
    return r.json() if r.status_code == 200 and r.text.strip()[:1] in "[{" else None


def dubai(cache, log=print):
    """DFM publishes each quarter the list of Shari'a-compliant companies on DFM and on Nasdaq Dubai."""
    prev = cache.get("AE") or {}
    try:
        periods = _dfm("Command=shariahlisting&Language=en")
    except Exception as e:
        log("    Dubai: request failed", e)
        periods = None
    if not isinstance(periods, list) or not periods:
        log("    Dubai: no list, keeping the last edition")
        return prev or None
    periods = [p for p in periods if isinstance(p, dict) and p.get("year") and p.get("quarter")]
    periods.sort(key=lambda p: p.get("date") or "", reverse=True)
    head = periods[0]
    date = head.get("date") or f"{head['year']}-Q{head['quarter']}"
    hist = {h[0]: h[1] for h in (prev.get("history") or []) if h[1] and re.match(r"\d{4}-\d\d-\d\d$", h[0]) and h[0] <= date}

    def get_list(p, ex):
        try:
            x = _dfm(f"Command=shariahlistingdetails&year={p['year']}&quarter={p['quarter']}&exchange={ex}&Language=en")
            return x if isinstance(x, list) else []
        except Exception as e:
            log("    Dubai: details failed", p, ex, e)
            return []

    if prev.get("asOf") == date and prev.get("count") and prev.get("v") == 2:
        rows = None
    else:
        rows = []
        for ex, label in (("dfm", "DFM"), ("nasdaq", "Nasdaq Dubai")):
            if ex in (head.get("exchanges") or []):
                for x in get_list(head, ex):
                    if x.get("name"):
                        rows.append({"c": str(x.get("symbol") or "").strip(), "n": str(x["name"]).strip(), "s": label})
        if not rows:
            log("    Dubai: empty list, keeping the last edition")
            return prev or None
        hist[date] = len(rows)
    # quarterly history: count the last eight editions once
    for p in periods[1:9]:
        d = p.get("date")
        if d and d not in hist:
            n = sum(len(get_list(p, ex)) for ex in ("dfm", "nasdaq") if ex in (p.get("exchanges") or []))
            if n:
                hist[d] = n
    if rows is None:
        prev["history"] = sorted([[k, v] for k, v in hist.items() if v])[-20:]
        prev["checked"] = dt.date.today().isoformat()
        return prev
    names = [x["n"] for x in rows]
    a, rm = _diff(prev.get("_names"), names) if prev.get("_names") else ([], [])
    ex = {}
    for x in rows:
        ex[x["s"]] = ex.get(x["s"], 0) + 1
    log(f"    Dubai {date}: {len(rows)} compliant companies ({ex})")
    return {
        "v": 2, "code": "AE", "market": "Dubai Financial Market and Nasdaq Dubai", "country": "United Arab Emirates",
        "authority": "DFM Fatwa and Shari'a Supervisory Board",
        "asOf": date, "quarter": f"Q{head['quarter']} {head['year']}", "checked": dt.date.today().isoformat(),
        "url": C.DFM_PAGE, "page": C.DFM_PAGE, "title": "Shari'a Classification List",
        "count": len(rows), "share": None,
        "addedCount": len(a) if prev.get("_names") else None, "removedCount": len(rm) if prev.get("_names") else None,
        "added": a[:60], "removed": rm[:60],
        "sectors": sorted([[k, v] for k, v in ex.items()], key=lambda kv: -kv[1]), "sectorsBy": "exchange",
        "history": sorted([[k, v] for k, v in hist.items() if v])[-20:],
        "list": [[x["c"], x["n"], x["s"]] for x in rows],
        "next": "Quarterly, after companies publish their results",
        "_names": names,
    }


def islamic_banks(lst):
    """Banks and financing companies on an official list (names that say Islamic, Syariah, Bank…)."""
    if not lst:
        return []
    pat = re.compile(r"islam|syariah|shariah|sharia|bank|takaful|muamalat|rajhi|financ", re.I)
    skip = re.compile(r"\betf\b|\bfund\b|share class|reit", re.I)
    return [row[1] for row in lst.get("list", []) if pat.search(row[1]) and not skip.search(row[1])][:40]
