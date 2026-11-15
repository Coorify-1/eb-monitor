"""Reader-facing text and number formats, generated from the data (no hand-written opinions)."""
import math
import re


def money(v, cur="USD"):
    if v is None or not math.isfinite(v):
        return "—"
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}.get(cur, cur + " ")
    a = abs(v)
    sign = "−" if v < 0 else ""
    if a >= 1e12:
        s = f"{a / 1e12:.1f}tn"
    elif a >= 1e9:
        s = f"{a / 1e9:.0f}bn" if a >= 100e9 else f"{a / 1e9:.1f}bn"
    elif a >= 1e6:
        s = f"{a / 1e6:.0f}mn"
    else:
        s = f"{a:,.0f}"
    return f"{sign}{sym}{s}"


def pct(v, d=1):
    return "—" if v is None or not math.isfinite(v) else f"{v * 100:.{d}f}%"


def mult(v, d=1):
    if v is None:
        return "—"
    if not math.isfinite(v):
        return "n/m"
    return f"{v:.{d}f}x"


SMALL = {"of", "and", "the", "de", "la", "du", "des", "y", "e"}
UPPER = {
    "PLC", "AG", "SA", "NV", "SE", "ASA", "AB", "ADR", "LLC", "LP", "II", "III", "US", "USA",
    "UBS", "HSBC", "ING", "BBVA", "ICICI", "HDFC", "BNP", "UK", "KB", "NA", "TD", "IBM", "AMD",
    "ASML", "SAP", "BHP", "BP", "NXP", "RELX", "ABB", "CRH", "TSMC", "ADP", "AT&T",
}


def nice_name(sec_name: str) -> str:
    n = re.sub(r"\s*/[A-Z]{2,}/?\s*$", "", sec_name.strip())  # "XYZ CORP /DE/"
    words = []
    for i, w in enumerate(n.split()):
        bare = w.strip(",.")
        if bare.upper() in UPPER:
            words.append(w.upper())
        elif i and bare.lower() in SMALL:
            words.append(w.lower())
        elif "&" in w and len(w) <= 4:
            words.append(w.upper())
        else:
            words.append(w[:1].upper() + w[1:].lower())
    return " ".join(words)


BANK_GOOD = {
    "valuation": "priced below peer banks",
    "momentum": "a strong share-price trend",
    "capital": "a strong capital buffer",
    "quality": "a clean loan book",
    "profit": "high returns on equity",
}
COMPANY_GOOD = {
    "valuation": "attractively priced cash flows",
    "momentum": "a strong share-price trend",
    "quality": "high returns on capital",
    "health": "a solid balance sheet",
}


def why(kind, row, pillars):
    good = BANK_GOOD if kind == "banking" else COMPANY_GOOD
    ranked = sorted(
        [(row.get("p_" + k), k) for k, _, _ in pillars if row.get("p_" + k) == row.get("p_" + k) and row.get("p_" + k) is not None],
        reverse=True,
    )
    top = [k for v, k in ranked[:2] if v >= 55]
    if not top:
        return "Balanced scores across all pillars."
    txt = good[top[0]]
    if len(top) > 1:
        txt += " and " + good[top[1]]
    r = row.get("ret_12m")
    extra = ""
    if "momentum" in top and r is not None and math.isfinite(r):
        extra = f" (shares {'+' if r >= 0 else '−'}{abs(r) * 100:.0f}% in 12 months)"
    return txt[0].upper() + txt[1:] + extra + "."


def risks(kind, row, currency):
    out = []
    if (row.get("p_momentum") or 50) < 40:
        out.append("The share-price trend is weaker than for most peers.")
    if (row.get("p_valuation") or 50) < 40:
        out.append("Priced above most peers, which leaves less room for disappointment.")
    if kind == "banking":
        npl, npl_p = row.get("npl"), row.get("npl_prev")
        if npl is not None and npl_p is not None and npl > npl_p * 1.1:
            out.append("Bad loans rose over the last year.")
        ci = row.get("cost_income")
        if ci is not None and math.isfinite(ci) and ci > 0.65:
            out.append(f"Costs are high: {ci * 100:.0f} cents per dollar of income.")
        if (row.get("p_capital") or 50) < 40:
            out.append("Capital buffer is thinner than at most peer banks.")
    else:
        nd = row.get("nd_ebitda")
        if nd is not None and math.isfinite(nd) and nd > 3:
            out.append(f"Debt is high: net debt is {nd:.1f} times yearly operating earnings (EBITDA).")
        rc = row.get("revenue_chg")
        if rc is not None and rc < 0:
            out.append(f"Revenue fell {abs(rc) * 100:.0f}% last year.")
        if (row.get("p_health") or 50) < 40:
            out.append("Balance-sheet strength is below most peers.")
    if currency and currency != "USD":
        out.append(f"Results are reported in {currency}: exchange-rate moves change returns in US dollars.")
    if not out:
        out.append("Scores compare companies with each other: a falling market can still pull this share down.")
    return out[:3]
