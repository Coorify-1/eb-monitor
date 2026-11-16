"""Islamic finance headlines of the last 24 to 48 hours from GDELT (free and open data).
Only the headline, the source and a link to the original article are shown."""
import re
import time
from urllib.parse import urlparse

import requests

from . import config as C

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def fetch(log=print, tries=6):
    for i in range(tries):
        try:
            r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", timeout=60,
                             headers={"User-Agent": BROWSER}, params={
                                 "query": C.NEWS_QUERY, "mode": "ArtList", "maxrecords": 75,
                                 "format": "json", "timespan": "48h", "sort": "DateDesc"})
            if r.status_code == 200 and r.text.strip().startswith("{"):
                return r.json().get("articles") or []
            log(f"    news: attempt {i + 1} -> {r.status_code}")
        except Exception as e:
            log(f"    news: attempt {i + 1} failed {e}")
        time.sleep(20 + 10 * i)
    return None


def tag_of(title):
    t = title.lower()
    for tag, pat in C.NEWS_TAGS:
        if re.search(pat, t):
            return tag
    return "Markets"


def clean(arts, keep):
    out, seen = [], set()
    must = re.compile(r"sukuk|islamic|shariah|sharia|syariah|halal|takaful|aaoifi|ifsb|zakat|waqf|murabaha|ijara", re.I)
    for a in arts:
        title = re.sub(r"\s+", " ", (a.get("title") or "")).strip()
        url = a.get("url") or ""
        if not title or not url or not must.search(title):
            continue
        key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
        dom = (a.get("domain") or urlparse(url).netloc).replace("www.", "")
        if key in seen:
            continue
        seen.add(key)
        sd = a.get("seendate") or ""
        iso = f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}T{sd[9:11]}:{sd[11:13]}:00Z" if len(sd) >= 13 else None
        out.append({"title": title[:180], "url": url, "source": dom, "date": iso, "tag": tag_of(title),
                    "country": a.get("sourcecountry") or ""})
        if len(out) >= keep:
            break
    return out


def update(cache, log=print):
    arts = fetch(log=log)
    if arts is None:
        log("    news: GDELT unavailable, keeping the last headlines")
        return cache.get("news") or [], False
    items = clean(arts, C.NEWS_MAX)
    if not items:
        return cache.get("news") or [], False
    cache["news"] = items
    return items, True
