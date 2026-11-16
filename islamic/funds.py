"""Islamic funds from their SEC Form N-PORT reports (public domain).

Each report gives the fund's net assets, its total return for each of the three months
of the period, and every holding. Reports become public about 60 days after month end.
"""
import re
import xml.etree.ElementTree as ET

from . import config as C


def _strip(xml_bytes):
    root = ET.fromstring(xml_bytes)
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
        for k in list(el.attrib):
            if "}" in k:
                el.attrib[k.split("}", 1)[1]] = el.attrib.pop(k)
    return root


def _txt(root, path):
    el = root.find(path)
    return el.text.strip() if el is not None and el.text else None


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def month_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7])
    m += k
    while m <= 0:
        y, m = y - 1, m + 12
    while m > 12:
        y, m = y + 1, m - 12
    return f"{y:04d}-{m:02d}"


def parse_nport(xml_bytes, class_id):
    root = _strip(xml_bytes)
    rep = _txt(root, ".//genInfo/repPdDate") or _txt(root, ".//genInfo/repPdEnd")
    net = _num(_txt(root, ".//fundInfo/netAssets"))
    months = {}
    for r in root.iter("monthlyTotReturn"):
        if class_id and r.attrib.get("classId") not in (class_id, None):
            continue
        if rep:
            ym = rep[:7]
            for k, key in ((-2, "rtn1"), (-1, "rtn2"), (0, "rtn3")):
                v = _num(r.attrib.get(key))
                if v is not None:
                    months[month_add(ym, k)] = v
        break
    hold = []
    for s in root.iter("invstOrSec"):
        pct = _num(_txt(s, "pctVal"))
        if pct is None:
            continue
        hold.append({
            "n": (_txt(s, "name") or _txt(s, "title") or "").strip()[:60],
            "pct": round(pct, 2),
            "cat": _txt(s, "assetCat") or "",
            "cc": _txt(s, "invCountry") or "",
        })
    hold.sort(key=lambda h: -h["pct"])
    countries = {}
    for h in hold:
        if h["cc"]:
            countries[h["cc"]] = countries.get(h["cc"], 0) + h["pct"]
    top_cc = sorted(countries.items(), key=lambda kv: -kv[1])[:6]
    return {
        "date": rep, "netAssets": net, "months": months, "n": len(hold),
        "top": [{"n": h["n"], "pct": h["pct"]} for h in hold[:10]],
        "countries": [[k, round(v, 1)] for k, v in top_cc],
    }


def series_filings(sec, series_id, count=40):
    """N-PORT filings of one fund series, newest first: [(date, index_url)]."""
    r = sec._get(
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK="
        f"{series_id}&type=NPORT-P&dateb=&owner=include&count={count}&output=atom"
    )
    if r is None:
        return []
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", r.text, re.S):
        href = re.search(r"<filing-href>(.*?)</filing-href>", e)
        date = re.search(r"<filing-date>(.*?)</filing-date>", e)
        typ = re.search(r"<filing-type>(.*?)</filing-type>", e)
        if href and (not typ or typ.group(1).startswith("NPORT-P")):
            out.append((date.group(1) if date else "", href.group(1)))
    return out


def primary_doc(sec, index_url):
    base = index_url.rsplit("/", 1)[0]
    r = sec._get(base + "/primary_doc.xml")
    return r.content if r is not None else None


def update(sec, mf_map, cache, log=print):
    """cache = {ticker: {"filings": {accession: parsed}}}; returns the published list."""
    out = []
    for t, name, issuer, kind in C.FUNDS:
        info = mf_map.get(t)
        if not info:
            log(f"    {t}: not found in the SEC fund list")
            continue
        fc = cache.setdefault(t, {"filings": {}})
        try:
            fl = series_filings(sec, info["seriesId"])
        except Exception as e:
            log(f"    {t}: filings list failed {e}")
            fl = []
        new = [x for x in fl if x[1] not in fc["filings"]]
        if not fc["filings"]:
            new = new[: C.FUND_FILINGS_BACKFILL]
        else:
            new = new[:4]
        for date, href in new:
            try:
                xml = primary_doc(sec, href)
                if xml:
                    p = parse_nport(xml, info.get("classId"))
                    p["filed"] = date
                    fc["filings"][href] = p
            except Exception as e:
                log(f"    {t}: report failed {href} {e}")
        reps = sorted(fc["filings"].values(), key=lambda p: (p.get("date") or "", p.get("filed") or ""))
        if not reps:
            continue
        months = {}
        for p in reps:  # newer reports overwrite older figures for the same month
            months.update(p.get("months") or {})
        last = reps[-1]
        nav = [[p["date"][:7], round(p["netAssets"] / 1e6, 1)] for p in reps if p.get("date") and p.get("netAssets")]
        out.append({
            "t": t, "name": name, "issuer": issuer, "kind": kind,
            "asOf": last.get("date"), "filed": last.get("filed"),
            "netAssets": round((last.get("netAssets") or 0) / 1e6, 1),
            "holdings": last.get("n"),
            "months": [[k, round(v, 2)] for k, v in sorted(months.items())][-48:],
            "assets": nav[-24:],
            "top": last.get("top", [])[:10],
            "countries": last.get("countries", []),
        })
        log(f"    {t}: {len(fc['filings'])} reports, last {last.get('date')}, {len(months)} months")
    return out
