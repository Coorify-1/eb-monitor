import os, re, requests
os.makedirs("probe", exist_ok=True)
B = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
s = requests.Session(); s.headers["User-Agent"] = B
r = s.get("https://www.sc.com.my/api/documentms/download.ashx?id=5f0bb08b-802c-49a0-b093-d6f0edf6c276", timeout=90)
open("probe/sc.pdf", "wb").write(r.content)
out = []
for page in ["https://www.dfm.ae/en/the-exchange/statistics-reports/sharia-classification-list",
             "https://www.dfm.ae/the-exchange/statistics-reports/sharia-classification-list"]:
    r = s.get(page, timeout=60); out.append(f"PAGE {page} {r.status_code} {len(r.text)}")
    open("probe/dfm_page.html", "w").write(r.text)
    js = set(re.findall(r'((?:https://[^"\']+)?/_nuxt/[^"\']+\.js)', r.text))
    out.append(f"{len(js)} js")
    for j in js:
        u = j if j.startswith("http") else "https://www.dfm.ae" + j
        t = s.get(u, timeout=60).text
        for m in re.finditer(r'.{0,500}(?:shariahlisting|sharia-classification|shariah).{0,800}', t, re.I):
            out.append(f"--- {j}\n{m.group(0)}")
open("probe/dfm.txt", "w").write("\n".join(out))
