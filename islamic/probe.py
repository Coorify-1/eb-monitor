import os, re, json, time, requests, sys
sys.path.insert(0, ".")
from islamic import lists as L, config as C
os.makedirs("probe", exist_ok=True)
B = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
def w(n, t): open(f"probe/{n}", "w").write(t if isinstance(t, str) else json.dumps(t, indent=1, default=str))
# 1 Malaysia lines
try:
    d = L.latest_sc_document(); w("sc_doc.txt", str(d))
    r = requests.get(d[1], headers={"User-Agent": B}, timeout=90)
    lines = L.pdf_lines(r.content); w("sc_lines.txt", "\n".join(lines))
except Exception as e: w("sc_err.txt", repr(e))
# 2 DFM bundle commands
out = []
try:
    s = requests.Session(); s.headers["User-Agent"] = B
    for page in ["https://www.dfm.ae/the-exchange/market-information/shariah-compliant-companies",
                 "https://www.dfm.ae/en/the-exchange/market-information/shariah-compliant-companies", "https://www.dfm.ae/"]:
        r = s.get(page, timeout=60); out.append(f"PAGE {page} {r.status_code} {len(r.text)}")
        js = set(re.findall(r'(/_nuxt/[^"\']+\.js)', r.text))
        for j in js:
            t = s.get("https://www.dfm.ae" + j, timeout=60).text
            for m in re.finditer(r'.{0,400}[Ss]hariah?[Ll]ist.{0,600}', t):
                out.append(f"--- {j}\n{m.group(0)}")
    hdr = {"Origin": "https://www.dfm.ae", "Referer": "https://www.dfm.ae/", "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    for body in ["Command=shariahlisting&Language=en", "Command=shariahlisting&Language=en&Year=2026&Quarter=2",
                 "Command=shariahlisting&Language=en&year=2026&quarter=2", "Command=shariahlistingdata&Language=en&Year=2026&Quarter=2",
                 "Command=shariahcompliant&Language=en&Year=2026&Quarter=2", "Command=shariahlisting&Language=en&Year=2026&Quarter=2&Exchange=dfm",
                 "Command=shariahlisting&Language=en&year=2026&quarter=2&exchange=dfm"]:
        r = s.post(C.DFM_API, data=body, headers=hdr, timeout=60); out.append(f"POST {body} -> {r.status_code} {r.text[:1500]}")
except Exception as e: out.append(repr(e))
w("dfm.txt", "\n".join(out))
# 3 news
res = []
for name, url, params in [
    ("gdelt", "https://api.gdeltproject.org/api/v2/doc/doc", {"query": C.NEWS_QUERY, "mode": "ArtList", "maxrecords": 30, "format": "json", "timespan": "48h"}),
    ("gnews", "https://news.google.com/rss/search", {"q": "sukuk OR \"islamic finance\" OR takaful when:2d", "hl": "en-US", "gl": "US", "ceid": "US:en"}),
    ("bing", "https://www.bing.com/news/search", {"q": "sukuk OR \"islamic finance\"", "format": "rss"}),
    ("ifn", "https://www.islamicfinancenews.com/feed", None), ("salaam", "https://www.salaamgateway.com/rss", None),
    ("zawya", "https://www.zawya.com/en/rss/islamic-economy", None), ("ifnmy", "https://www.islamicfinancenews.com/rss", None),
    ("theedge", "https://theedgemalaysia.com/rss", None), ("arabnews", "https://www.arabnews.com/cat/3/rss.xml", None),
    ("nst", "https://www.nst.com.my/business/rss.xml", None), ("gulfnews", "https://gulfnews.com/rss/business", None),
]:
    try:
        r = requests.get(url, params=params, headers={"User-Agent": B}, timeout=40)
        res.append(f"== {name} {r.status_code} {r.headers.get('content-type')} {len(r.text)}\n{r.text[:1500]}")
    except Exception as e: res.append(f"== {name} {e!r}")
    time.sleep(6)
w("news.txt", "\n\n".join(res))
