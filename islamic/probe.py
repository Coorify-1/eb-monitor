"""One-off probe: fetch every planned source and save what comes back (for building parsers)."""
import json, os, re, traceback
import requests

OUT = "probe"
os.makedirs(OUT, exist_ok=True)
UA = os.environ.get("SEC_CONTACT", "").strip() or "Economic Bearings research"
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
log = open(f"{OUT}/log.txt", "w")

def note(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True); log.write(s + "\n"); log.flush()

def get(url, name=None, ua=BROWSER, **kw):
    try:
        r = requests.get(url, headers={"User-Agent": ua, **kw.pop("headers", {})}, timeout=60, **kw)
        note(f"GET {url} -> {r.status_code} {r.headers.get('content-type')} {len(r.content)}B")
        if name:
            open(f"{OUT}/{name}", "wb").write(r.content[:3_000_000])
        return r
    except Exception as e:
        note(f"GET {url} FAILED {e}")
        return None

def links(html, pat):
    return sorted(set(re.findall(r'(?:href|src)=["\']([^"\']*%s[^"\']*)["\']' % pat, html, re.I)))

def pdftext(r, name, pages=4):
    try:
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            note(f"  {name}: {len(pdf.pages)} pages")
            txt = "\n\n=== PAGE ===\n".join((p.extract_text() or "") for p in pdf.pages[:pages])
            last = pdf.pages[-1].extract_text() or ""
        open(f"{OUT}/{name}.txt", "w").write(txt + "\n\n=== LAST PAGE ===\n" + last)
    except Exception as e:
        note("  pdf failed", e)

# 1 Malaysia SC
r = get("https://www.sc.com.my/development/icm/icm-publications/list-of-shariah-compliant-securities", "sc.html")
if r is not None:
    pdfs = links(r.text, r"\.pdf") + links(r.text, "api/documentms")
    note("  SC links:", pdfs[:40])
r = get("https://www.sc.com.my/development/icm/shariah-compliant-securities", "sc2.html")
if r is not None:
    note("  SC2 links:", (links(r.text, r"\.pdf") + links(r.text, "documentms"))[:40])
    for u in [x for x in links(r.text, "list") ][:15]:
        note("   list-ish:", u)

# 2 Indonesia OJK
for u in ["https://www.ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Default.aspx",
          "https://ojk.go.id/id/berita-dan-kegiatan/pengumuman/Pages/Daftar-Efek-Syariah-KEP21D042026.aspx"]:
    r = get(u, "ojk_" + str(abs(hash(u)) % 1000) + ".html")
    if r is not None:
        note("  OJK links:", (links(r.text, r"\.pdf") + links(r.text, "Daftar-Efek-Syariah"))[:40])
r = get("https://www.ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Documents/Pages/Daftar-Efek-Syariah-KEP21D042026/SK%20DES%20Periode%20I%202026.pdf")
if r is not None and r.status_code == 200:
    pdftext(r, "ojk_des", pages=6)
r = get("https://idx.id/media/nbkfn2sd/des-mei-2026.pdf")
if r is not None and r.status_code == 200:
    pdftext(r, "idx_des", pages=3)

# 3 Dubai DFM
r = get("https://www.dfm.ae/en/the-exchange/statistics-reports/sharia-classification-list", "dfm.html")
if r is not None:
    note("  DFM api-ish:", sorted(set(re.findall(r'https?://[a-z0-9.\-]*dfm\.ae/[^"\'\s<>]{0,120}', r.text)))[:60])
    note("  DFM scripts:", links(r.text, r"\.js")[:30])
for u in ["https://api2.dfm.ae/web/widgets/v1/data", "https://api.dfm.ae/web/widgets/v1/data"]:
    get(u)

# 4 BNM
H = {"Accept": "application/vnd.BNM.API.v1+json"}
for path in ["islamic-interbank-rate", "myor-i", "myor", "kijang-emas", "opr"]:
    get("https://api.bnm.gov.my/public/" + path, "bnm_" + path + ".json", headers=H)
r = get("https://www.bnm.gov.my/-/bnm-openapi", "bnm_openapi.html")
if r is not None:
    note("  BNM terms links:", [x for x in links(r.text, "term")][:20])

# 5 GDELT
get("https://api.gdeltproject.org/api/v2/doc/doc", "gdelt.json", ua=UA, params={
    "query": '(sukuk OR "islamic finance" OR "islamic bank" OR "shariah-compliant" OR "sharia-compliant" OR takaful OR AAOIFI OR IFSB) sourcelang:english',
    "mode": "ArtList", "maxrecords": 50, "format": "json", "timespan": "48h", "sort": "DateDesc"})

# 6 SEC funds
r = get("https://www.sec.gov/files/company_tickers_mf.json", None, ua=UA)
want = ["SPUS", "HLAL", "SPSK", "UMMA", "SPRE", "SPTE", "SPWO", "MNZL", "AMAGX", "AMANX", "AMDWX", "AMAPX", "IGDA", "ISWD"]
found = {}
if r is not None:
    j = r.json(); f = j["fields"]
    for row in j["data"]:
        d = dict(zip(f, row))
        if d.get("symbol") in want:
            found[d["symbol"]] = d
    note("  MF found:", json.dumps(found))
    json.dump(found, open(f"{OUT}/funds.json", "w"), indent=1)
if "SPUS" in found:
    sid = found["SPUS"]["seriesId"]
    r = get(f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={sid}&type=NPORT-P&dateb=&owner=include&count=40&output=atom", "nport_atom.xml", ua=UA)
    if r is not None:
        hrefs = re.findall(r"<filing-href>(.*?)</filing-href>", r.text) or re.findall(r'href="([^"]+-index\.htm)"', r.text)
        note("  NPORT filings:", hrefs[:8])
        if hrefs:
            idx = get(hrefs[0], "nport_index.html", ua=UA)
            if idx is not None:
                xmls = links(idx.text, r"\.xml")
                note("  xml:", xmls)
                if xmls:
                    get("https://www.sec.gov" + xmls[0] if xmls[0].startswith("/") else xmls[0], "nport_primary.xml", ua=UA)
note("done")
