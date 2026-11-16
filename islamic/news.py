"""Islamic finance headlines, from free and open sources.

- GDELT DOC API (open data, often rate-limited from shared cloud machines)
- public RSS feeds of business news sites, filtered on Islamic finance words

Only the headline, the source and a link to the original article are shown. Headlines are kept for
NEWS_DAYS days, so the panel still has the latest stories on quiet days.
"""
import datetime as dt
import email.utils
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

from . import config as C

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
MUST = re.compile(
    r"sukuk|islamic (bank|financ|fund|develop|econom|capital|insur|window|bond)|shariah|sharia|syariah|takaful|aaoifi|"
    r"\bifsb\b|zakat|waqf|murabaha|ijara|musharakah|mudarabah|halal (invest|fund|etf|stock)|\bisdb\b|al rajhi|"
    r"dubai islamic|kuwait finance house|bank islam|maybank islamic|cimb islamic|bank syariah|alinma|al baraka|meezan", re.I)


def gdelt(log=print, tries=6, span="72h"):
    for i in range(tries):
        try:
            r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", timeout=60,
                             headers={"User-Agent": BROWSER}, params={
                                 "query": C.NEWS_QUERY, "mode": "ArtList", "maxrecords": 75,
                                 "format": "json", "timespan": span, "sort": "DateDesc"})
            if r.status_code == 200 and r.text.strip().startswith("{"):
                out = []
                for a in r.json().get("articles") or []:
                    sd = a.get("seendate") or ""
                    iso = f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}T{sd[9:11]}:{sd[11:13]}:00Z" if len(sd) >= 13 else None
                    out.append({"title": a.get("title") or "", "url": a.get("url") or "", "date": iso,
                                "source": (a.get("domain") or "").replace("www.", ""), "country": a.get("sourcecountry") or ""})
                return out
            log(f"    news: GDELT attempt {i + 1} -> {r.status_code}")
        except Exception as e:
            log(f"    news: GDELT attempt {i + 1} failed {e}")
        time.sleep(10 + 10 * i)
    return []


def _iso(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")


def rss(log=print):
    out = []
    for name, url in C.NEWS_FEEDS:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": BROWSER, "Accept": "application/rss+xml, application/xml, text/xml"})
            if r.status_code != 200:
                log(f"    news: {name} -> {r.status_code}")
                continue
            root = ET.fromstring(r.content)
        except Exception as e:
            log(f"    news: {name} failed {e}")
            continue
        n = 0
        for it in root.iter():
            if it.tag.split("}")[-1] not in ("item", "entry"):
                continue
            f = {c.tag.split("}")[-1]: c for c in it}
            title = (f["title"].text if "title" in f else "") or ""
            link = f.get("link")
            href = (link.text or link.get("href") or "") if link is not None else ""
            date = next((f[k].text for k in ("pubDate", "published", "updated", "date") if k in f), None)
            out.append({"title": title, "url": href.strip(), "date": _iso(date), "source": urlparse(href).netloc.replace("www.", ""),
                        "country": ""})
            n += 1
        log(f"    news: {name} {n} items")
    return out


def tag_of(title):
    t = title.lower()
    for tag, pat in C.NEWS_TAGS:
        if re.search(pat, t):
            return tag
    return "Markets"


def clean(arts):
    out, seen = [], set()
    for a in arts:
        title = re.sub(r"\s+", " ", a.get("title") or "").strip()
        url = a.get("url") or ""
        if not title or not url.startswith("http") or not MUST.search(title):
            continue
        key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title[:180], "url": url, "source": a.get("source") or urlparse(url).netloc.replace("www.", ""),
                    "date": a.get("date"), "tag": tag_of(title), "country": a.get("country") or ""})
    return out


def update(cache, log=print, now=None):
    """Returns (headlines, fresh): fresh is True when at least one headline is less than 48 hours old."""
    now = now or dt.datetime.now(dt.timezone.utc)
    new = clean(rss(log=log) + gdelt(log=log))
    log(f"    news: {len(new)} Islamic finance headlines found today")
    old = cache.get("items") or cache.get("news") or []
    cut = (now - dt.timedelta(days=C.NEWS_DAYS)).strftime("%Y-%m-%dT%H:%M:00Z")
    stamp = now.strftime("%Y-%m-%dT%H:%M:00Z")
    for x in new:
        x["date"] = x.get("date") or stamp
    items = clean(sorted(new + old, key=lambda x: x.get("date") or "", reverse=True))
    items = [x for x in items if (x.get("date") or "") >= cut][:C.NEWS_KEEP]
    cache["items"] = items
    cache.pop("news", None)
    fresh_cut = (now - dt.timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:00Z")
    fresh = any((x.get("date") or "") >= fresh_cut for x in items)
    return items[:C.NEWS_MAX], fresh
