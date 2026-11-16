import os, re, json, time, requests, sys
sys.path.insert(0, ".")
from islamic import config as C
os.makedirs("probe", exist_ok=True)
B = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
out = []
for q in ["sukuk", "sukuk sourcelang:english", "(sukuk OR takaful OR \"islamic finance\") sourcelang:english", C.NEWS_QUERY]:
    for i in range(6):
        r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", headers={"User-Agent": B}, timeout=60,
                         params={"query": q, "mode": "ArtList", "maxrecords": 50, "format": "json", "timespan": "72h", "sort": "DateDesc"})
        if r.status_code == 200: break
        time.sleep(12)
    try: arts = r.json().get("articles") or []
    except Exception: arts = []; out.append(r.text[:300])
    out.append(f"== {q} -> {r.status_code} {len(arts)}\n" + "\n".join(f"{a.get('seendate')} {a.get('domain')} | {a.get('title')}" for a in arts[:15]))
    time.sleep(8)
r = requests.get(C.FX_FALLBACK, timeout=30); out.append(f"FX {r.status_code} TWD={(r.json().get('usd') or {}).get('twd')}")
h = {"User-Agent": "EB research contact@example.com"}
f = requests.get("https://data.sec.gov/api/xbrl/companyfacts/CIK0001046179.json", headers={"User-Agent": os.environ.get("SEC_CONTACT") or "EB bot eb@example.com"}, timeout=60)
j = f.json(); ifrs = (j.get("facts") or {}).get("ifrs-full") or {}
out.append(f"TSM facts {f.status_code} taxonomies {list((j.get('facts') or {}).keys())} cash {list((ifrs.get('CashAndCashEquivalents') or {}).get('units', {}).keys())}")
for k in ("CashAndCashEquivalents",):
    rows = ifrs.get(k, {}).get("units", {}).get("TWD", [])
    out.append(str(rows[-3:]))
b = requests.get("https://api.bnm.gov.my/public/islamic-interbank-rate", headers={"Accept": "application/vnd.BNM.API.v1+json"}, timeout=30)
out.append("BNM " + b.text[:800])
open("probe/out.txt", "w").write("\n\n".join(out))
