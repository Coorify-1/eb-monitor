import os, re, requests, html
os.makedirs("probe", exist_ok=True)
B = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
KW = re.compile(r"sukuk|islamic|shariah|sharia|syariah|halal|takaful|aaoifi|ifsb|zakat|waqf|murabaha|ijara", re.I)
feeds = {
 "zawya_ie": "https://www.zawya.com/en/rss/islamic-economy", "zawya_if": "https://www.zawya.com/en/rss/islamic-finance",
 "zawya_bus": "https://www.zawya.com/en/rss/business", "salaam": "https://www.salaamgateway.com/feed",
 "salaam3": "https://salaamgateway.com/rss.xml", "ethica": "https://www.ethica.institute/blog-feed.xml",
 "saudigazette": "https://saudigazette.com.sa/rss", "meed": "https://www.meed.com/feed",
 "bt_my": "https://www.businesstoday.com.my/feed/", "btimes_my": "https://www.nst.com.my/rss/business",
 "thestar2": "https://www.thestar.com.my/rss/Business/Business-News", "edge2": "https://theedgemalaysia.com/feed",
 "mubasher": "https://english.mubasher.info/rss/news", "arabnews": "https://www.arabnews.com/rss.xml",
 "gulftimes": "https://www.gulf-times.com/rss/business", "peninsula": "https://thepeninsulaqatar.com/rss/business",
 "kuwaittimes": "https://kuwaittimes.com/feed/", "omanobserver": "https://www.omanobserver.om/rss/business",
 "brecorder": "https://www.brecorder.com/feeds/latest-news", "thenews_pk": "https://www.thenews.com.pk/rss/2/16",
 "dailysabah": "https://www.dailysabah.com/rss/business", "jakpost": "https://www.thejakartapost.com/feed/business",
 "tempo": "https://en.tempo.co/rss/business", "emirates247": "https://www.emirates247.com/rss/business",
 "wam": "https://www.wam.ae/en/rss/economy", "spa": "https://www.spa.gov.sa/en/rss", "ifnfintech": "https://www.ifnfintech.com/feed/",
 "islamicmarkets": "https://islamicmarkets.com/feed", "cmo": "https://www.cmo.co.uk/feed",
}
ITEM = re.compile(r"<(item|entry)\b.*?</\1>", re.S | re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
DATE = re.compile(r"<(pubDate|published|updated|dc:date)[^>]*>(.*?)</\1>", re.S | re.I)
out = []
for k, u in feeds.items():
    try:
        r = requests.get(u, headers={"User-Agent": B}, timeout=30)
        items = []
        for m in ITEM.finditer(r.text):
            t = TITLE.search(m.group(0)); d = DATE.search(m.group(0))
            tt = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1))).strip() if t else ""
            items.append(((d.group(2) if d else "").strip(), tt))
        hits = [x for x in items if KW.search(x[1])]
        out.append(f"== {k} {r.status_code} items={len(items)} hits={len(hits)} first={items[0][0] if items else ''}\n" + "\n".join(f"   {d} | {t}" for d, t in hits[:5]))
    except Exception as e:
        out.append(f"== {k} ERR {type(e).__name__}")
open("probe/feeds2.txt", "w").write("\n".join(out))
