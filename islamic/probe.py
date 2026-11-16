"""Probe 2: DFM api, SC latest list, OJK listing, BNM history + terms, GDELT retry, IDX table pages."""
import json, os, re, time, io
import requests
OUT = "probe"; os.makedirs(OUT, exist_ok=True)
UA = os.environ.get("SEC_CONTACT", "").strip() or "Economic Bearings research"
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
log = open(f"{OUT}/log.txt", "w")
def note(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.write(s + "\n"); log.flush()
def get(url, name=None, ua=BROWSER, **kw):
    try:
        r = requests.get(url, headers={"User-Agent": ua, **kw.pop("headers", {})}, timeout=60, **kw)
        note(f"GET {url} -> {r.status_code} {r.headers.get('content-type')} {len(r.content)}B")
        if name: open(f"{OUT}/{name}", "wb").write(r.content[:3_000_000])
        return r
    except Exception as e:
        note(f"GET {url} FAILED {e}"); return None
def pdftext(r, name, pages=None):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        note(f"  {name}: {len(pdf.pages)} pages")
        ps = pdf.pages if pages is None else [pdf.pages[i] for i in pages if i < len(pdf.pages)]
        txt = "\n=== PAGE ===\n".join((p.extract_text() or "") for p in ps)
    open(f"{OUT}/{name}.txt", "w").write(txt)

# DFM: find the sharia api in bundles
r = get("https://www.dfm.ae/en/the-exchange/statistics-reports/sharia-classification-list")
hits = []
if r is not None:
    for js in sorted(set(re.findall(r'/_nuxt/[A-Za-z0-9_\-]+\.js', r.text))):
        x = get("https://www.dfm.ae" + js)
        if x is None: continue
        for m in re.finditer(r'(?i)shari', x.text):
            hits.append(js + " :: " + x.text[max(0, m.start()-250): m.start()+250].replace("\n", " "))
open(f"{OUT}/dfm_hits.txt", "w").write("\n\n".join(hits))
note("  DFM hits:", len(hits))
for u in ["https://api2.dfm.ae/web/widgets/v1/data?Command=GetShariaClassification&Lang=en",
          "https://api2.dfm.ae/web/sf/v1/sharia-classification-list", "https://api2.dfm.ae/web/widgets/v1/sharia"]:
    get(u, "dfm_try_" + str(abs(hash(u)) % 1000) + ".json", headers={"Origin": "https://www.dfm.ae", "Referer": "https://www.dfm.ae/"})

# SC: media releases + search for latest list
for u in ["https://www.sc.com.my/resources/media/media-release",
          "https://www.sc.com.my/resources/media/media-release/updated-list-of-shariah-compliant-securities-by-scs-shariah-advisory-council"]:
    r = get(u, "scm_" + str(abs(hash(u)) % 1000) + ".html")
    if r is not None:
        note("  2026 mentions:", sorted(set(re.findall(r'[^"<>]{0,80}(?:Shariah|shariah)[^"<>]{0,80}2026[^"<>]{0,40}', r.text)))[:10])
        note("  docs:", sorted(set(re.findall(r'documentms/download\.ashx\?id=[0-9a-fA-F-]+', r.text)))[:10])
r = get("https://www.sc.com.my/api/documentms/download.ashx?id=5f0bb08b-802c-49a0-b093-d6f0edf6c276")
if r is not None and r.status_code == 200 and r.content[:4] == b"%PDF":
    pdftext(r, "sc_list", pages=[0, 1, 2, 3, 4, 5])

# OJK listing pages
r = get("https://www.ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Default.aspx")
if r is not None:
    pages = sorted(set(re.findall(r'/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/[^"\']+\.aspx', r.text)))
    note("  OJK pages:", pages)
    p = get("https://www.ojk.go.id/id/kanal/syariah/data-dan-statistik/daftar-efek-syariah/Pages/Daftar-Efek-Syariah-KEP21D042026.aspx", "ojk_kep.html")
    if p is not None:
        note("  KEP pdfs:", sorted(set(re.findall(r'[^"\']*\.pdf', p.text)))[:10])
r = get("https://idx.id/media/nbkfn2sd/des-mei-2026.pdf")
if r is not None and r.status_code == 200:
    pdftext(r, "idx_des_tables", pages=[3, 4, 5, 18, 19])
r = get("https://www.idx.co.id/id/data-pasar/data-saham/indeks-saham/", "idx_index.html")

# BNM
H = {"Accept": "application/vnd.BNM.API.v1+json"}
get("https://api.bnm.gov.my/public/islamic-interbank-rate/year/2026/month/10", "bnm_iir_hist.json", headers=H)
get("https://api.bnm.gov.my/public/opr/year/2025", "bnm_opr_hist.json", headers=H)
get("https://api.bnm.gov.my/public/interest-rate", "bnm_ir.json", headers=H)
r = get("https://www.bnm.gov.my/terms-of-use-bnm-datasets", "bnm_terms.html")
if r is not None:
    t = re.sub(r"<[^>]+>", " ", r.text); t = re.sub(r"\s+", " ", t)
    i = t.find("Terms of Use"); open(f"{OUT}/bnm_terms.txt", "w").write(t[i:i+8000])

# GDELT with polite retries
for k in range(4):
    time.sleep(8)
    r = get("https://api.gdeltproject.org/api/v2/doc/doc", "gdelt.json", ua=UA, params={
        "query": '(sukuk OR "islamic finance" OR "islamic bank" OR "islamic banking" OR "shariah-compliant" OR "sharia-compliant" OR takaful OR AAOIFI OR IFSB) sourcelang:english',
        "mode": "ArtList", "maxrecords": 50, "format": "json", "timespan": "48h", "sort": "DateDesc"})
    if r is not None and r.status_code == 200: break
note("done")
