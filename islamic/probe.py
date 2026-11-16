import os, re, requests
os.makedirs("probe", exist_ok=True)
B = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
s = requests.Session(); s.headers["User-Agent"] = B
page = "https://www.dfm.ae/en/the-exchange/statistics-reports/sharia-classification-list"
html = s.get(page, timeout=60).text
todo = set(re.findall(r'/_nuxt/([A-Za-z0-9_\-]+\.js)', html)); done = set(); out = []
while todo and len(done) < 400:
    j = todo.pop(); done.add(j)
    try: t = s.get("https://www.dfm.ae/_nuxt/" + j, timeout=60).text
    except Exception: continue
    for n in re.findall(r'["\'`(./]+([A-Za-z0-9_\-]{6,12}\.js)', t):
        if n not in done: todo.add(n)
    for m in re.finditer(r'(?i)shariahlisting|sharialisting|shariah_listing', t):
        out.append(f"=== {j}\n" + t[max(0, m.start()-2500): m.end()+2500])
out.insert(0, f"{len(done)} chunks")
open("probe/dfm.txt", "w").write("\n".join(out))
