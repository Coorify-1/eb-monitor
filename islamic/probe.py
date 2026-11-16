import os, sys, json, datetime as dt, requests
sys.path.insert(0, ".")
from islamic import screen as S, config as C
os.makedirs("probe", exist_ok=True)
H = {"User-Agent": os.environ.get("SEC_CONTACT") or "EB research eb@example.com"}
fx = {"USD": 1, "TWD": 32.9, "JPY": 155, "INR": 88, "EUR": 0.86}
out = []
for cik in (1046179, 1094517, 75362, 1067491, 313838):
    j = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers=H, timeout=60).json()
    out.append(f"#### {cik} {j.get('entityName')} {list((j.get('facts') or {}).keys())}")
    out.append("inputs " + json.dumps(S.facts_inputs(j, fx, dt.date(2026, 11, 16))))
    for tax in ("ifrs-full", "us-gaap"):
        f = (j.get("facts") or {}).get(tax) or {}
        for tag in ["CashAndCashEquivalents", "CashAndCashEquivalentsAtCarryingValue", "Revenue", "Revenues", "Borrowings", "LongTermDebtNoncurrent", "NoncurrentPortionOfNoncurrentBorrowings"]:
            if tag in f:
                for u, rows in f[tag]["units"].items():
                    last = sorted(rows, key=lambda r: r.get("end", ""))[-3:]
                    out.append(f"  {tax}:{tag} {u} " + " ; ".join(f"{r.get('end')} {r.get('form')} {r.get('fp')} {r.get('start','')}" for r in last))
    # which forms exist
    forms = {}
    for tax, tags in (j.get("facts") or {}).items():
        for t, v in tags.items():
            for u, rows in v["units"].items():
                for r in rows:
                    forms[r.get("form")] = max(forms.get(r.get("form"), ""), r.get("end", ""))
    out.append("  forms " + json.dumps(forms))
open("probe/facts.txt", "w").write("\n".join(out))
