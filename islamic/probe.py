import os, re, requests, time
import xml.etree.ElementTree as ET
os.makedirs("probe", exist_ok=True)
B = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
KW = re.compile(r"sukuk|islamic|shariah|sharia|syariah|halal|takaful|aaoifi|ifsb|zakat|waqf|murabaha|ijara", re.I)
feeds = {
 "salaam": "https://salaamgateway.com/rss", "salaam2": "https://www.salaamgateway.com/feed",
 "islamicfinance": "https://www.islamicfinance.com/feed/", "ethica": "https://www.ethica.institute/blog-feed.xml",
 "zawya": "https://www.zawya.com/en/rss", "zawya2": "https://www.zawya.com/en/rss/islamic-economy",
 "national": "https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml",
 "national_biz": "https://www.thenationalnews.com/arc/outboundfeeds/rss/category/business/?outputType=xml",
 "khaleej": "https://www.khaleejtimes.com/rss/business", "gulfbusiness": "https://gulfbusiness.com/feed/",
 "arabianbusiness": "https://www.arabianbusiness.com/feed", "agbi": "https://www.agbi.com/feed/",
 "thestar": "https://www.thestar.com.my/rss/business", "malaymail": "https://www.malaymail.com/feed/rss/money",
 "bernama": "https://www.bernama.com/en/rss/news.php?cat=bu", "nst": "https://www.nst.com.my/feed",
 "freemalaysia": "https://www.freemalaysiatoday.com/category/business/feed/", "edge": "https://theedgemalaysia.com/rss.xml",
 "antara": "https://en.antaranews.com/rss/business.xml", "jakglobe": "https://jakartaglobe.id/rss",
 "dawn": "https://www.dawn.com/feeds/business", "tribune": "https://tribune.com.pk/feed/business",
 "saudigazette": "https://saudigazette.com.sa/rss", "argaam": "https://www.argaam.com/en/rss",
 "isdb": "https://www.isdb.org/rss.xml", "bnm": "https://www.bnm.gov.my/rss", "ifsb": "https://www.ifsb.org/feed/",
 "aaoifi": "https://aaoifi.com/feed/", "gulfnews": "https://gulfnews.com/rss/business",
 "tradearabia": "https://www.tradearabia.com/rss/", "meed": "https://www.meed.com/feed",
}
out = []
for k, u in feeds.items():
    try:
        r = requests.get(u, headers={"User-Agent": B, "Accept": "application/rss+xml, application/xml, text/xml"}, timeout=30)
        items = []
        if r.status_code == 200 and "<" in r.text[:100]:
            try:
                root = ET.fromstring(r.content)
                for it in root.iter():
                    if it.tag.split('}')[-1] in ("item", "entry"):
                        t = next((c.text for c in it if c.tag.split('}')[-1] == "title"), "") or ""
                        d = next((c.text for c in it if c.tag.split('}')[-1] in ("pubDate", "published", "updated", "date")), "") or ""
                        items.append((d, t.strip()))
            except Exception as e:
                out.append(f"{k} parse {e}")
        hits = [x for x in items if KW.search(x[1])]
        cr = re.search(r"<copyright>([^<]{0,200})", r.text)
        out.append(f"== {k} {r.status_code} items={len(items)} hits={len(hits)} last={items[0][0] if items else ''} copyright={cr.group(1) if cr else ''}\n" + "\n".join(f"   {d} | {t}" for d, t in hits[:6]))
    except Exception as e:
        out.append(f"== {k} ERR {e!r}")
open("probe/feeds.txt", "w").write("\n".join(out))
