"""THE ANALYST — settings.

Everything a non-developer may want to change lives here or in transmission.json:
data addresses, the assets followed, the pages they link to, and the thresholds.
"""

# ------------------------------------------------------------------ data addresses
# Economic Bearings Workers (the same ones the Framer pages use)
MARKET_WORKER = "https://marketdata.b-boussoffara.workers.dev"
METALS_WORKER = "https://metals.b-boussoffara.workers.dev"
ESTATE_WORKER = "https://real-estates.b-boussoffara.workers.dev"

# JSON already published by the other EB engines
ISLAMIC_JSON = "https://raw.githubusercontent.com/Coorify-1/eb-monitor/main/docs/eb-islamic.json"
MONITOR_JSON = "https://raw.githubusercontent.com/Coorify-1/eb-monitor/main/docs/eb-monitor.json"
OUTLOOK_JSON = "https://raw.githubusercontent.com/Coorify-1/eb-outlook/main/docs/eb-outlook.json"

# Public APIs used by the Crypto & Currencies and Energy pages
CEII_API = "https://terminal.centreforenergy.org/api/v1"
COINGECKO = "https://api.coingecko.com/api/v3"
FRANKFURTER = "https://api.frankfurter.dev/v1"

# ------------------------------------------------------------------ pages
# key used in the text  ->  page on economicbearings (the Framer component maps key -> slug)
PAGES = {
    "markets": "/market-data",
    "energy": "/energy-terminal",
    "crypto": "/crypto-currencies",
    "metals": "/hard-assets-terminal",
    "estate": "/estate-index",
    "corporate": "/corporate-monitor",
    "outlook": "/market-outlook",
    "islamic": "/islamic-investment",
}
PAGE_NAMES = {
    "markets": "Financial Markets",
    "energy": "Energy Terminal",
    "crypto": "Crypto & Currencies",
    "metals": "Hard Assets Terminal",
    "estate": "Estate Index",
    "corporate": "Corporate Monitor",
    "outlook": "Market Outlook",
    "islamic": "Islamic Investment",
}

# ------------------------------------------------------------------ assets followed
# kind: "price" (moves in %) or "yield" (moves in basis points)
# src : market (Worker, FRED symbols), fx (Frankfurter), crypto (CoinGecko), metals (Worker), eq (EB US 100)
ASSETS = [
    # id          name                         class        page       src       symbol                kind    unit
    ("us_eq",    "US large caps (EB US 100)",  "equities",  "markets", "eq",     "market",             "price", ""),
    ("shariah",  "EB Shariah US 100",          "equities",  "islamic", "eq",     "shariah",            "price", ""),
    ("vix",      "VIX volatility index",       "equities",  "markets", "market", "FRED:VIXCLS",        "price", ""),
    ("us2y",     "US 2-year yield",            "rates",     "markets", "market", "FRED:DGS2",          "yield", "%"),
    ("us10y",    "US 10-year yield",           "rates",     "markets", "market", "FRED:DGS10",         "yield", "%"),
    ("us30y",    "US 30-year yield",           "rates",     "markets", "market", "FRED:DGS30",         "yield", "%"),
    ("brent",    "Brent crude",                "energy",    "energy",  "market", "FRED:DCOILBRENTEU",  "price", "$"),
    ("wti",      "WTI crude",                  "energy",    "energy",  "market", "FRED:DCOILWTICO",    "price", "$"),
    ("natgas",   "US natural gas (Henry Hub)", "energy",    "energy",  "market", "FRED:DHHNGSP",       "price", "$"),
    ("gold",     "Gold",                       "metals",    "metals",  "metals", "gold",               "price", "$"),
    ("silver",   "Silver",                     "metals",    "metals",  "metals", "silver",             "price", "$"),
    ("platinum", "Platinum",                   "metals",    "metals",  "metals", "platinum",           "price", "$"),
    ("copper",   "Copper",                     "metals",    "metals",  "metals", "copper",             "price", "$"),
    ("eurusd",   "EUR/USD",                    "fx",        "crypto",  "fx",     "EUR",                "price", ""),
    ("usdjpy",   "USD/JPY",                    "fx",        "crypto",  "fx",     "JPY",                "price", ""),
    ("gbpusd",   "GBP/USD",                    "fx",        "crypto",  "fx",     "GBP",                "price", ""),
    ("usdchf",   "USD/CHF",                    "fx",        "crypto",  "fx",     "CHF",                "price", ""),
    ("usdcny",   "USD/CNY",                    "fx",        "crypto",  "fx",     "CNY",                "price", ""),
    ("btc",      "Bitcoin",                    "crypto",    "crypto",  "crypto", "bitcoin",            "price", "$"),
    ("eth",      "Ether",                      "crypto",    "crypto",  "crypto", "ethereum",           "price", "$"),
]

# Usual daily move when no history is available (stdev of 1-day change; % or bp)
DEFAULT_VOL = {
    "equities": 1.0, "rates": 6.0, "credit": 5.0, "energy": 2.0, "metals": 1.2,
    "fx": 0.5, "crypto": 3.0,
}
DEFAULT_VOL_ASSET = {"vix": 6.0, "natgas": 4.0, "silver": 2.2, "usdcny": 0.2}

# The six key figures at the top of the page, and the bars of chart 1
KPIS = ["us_eq", "us10y", "brent", "gold", "eurusd", "btc"]
CHART_BARS = ["us_eq", "vix", "us2y", "us10y", "us30y", "brent", "natgas", "gold",
              "silver", "copper", "eurusd", "usdjpy", "btc", "eth"]

# ------------------------------------------------------------------ thresholds
Z_NOTABLE = 1.0      # move larger than the usual daily swing
Z_SHARP = 2.0        # twice the usual daily swing
NEWS_SPIKE = 1.6     # news volume vs. its recent normal to call a theme "heating up"
CONFIRM_ASSETS = 2   # linked assets that must move the expected way to confirm a theme
CONFIRM_Z = 0.8

# ------------------------------------------------------------------ writing (free AI)
# OpenAI-compatible endpoint of Google's Gemini API, free tier (key from Google AI Studio,
# stored as the GitHub secret GEMINI_API_KEY). Models are tried in order.
# (GitHub Models, the first choice at design time, was shut down by GitHub on 30 July 2026.)
LLM_PROVIDERS = [
    {"name": "Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
     "env": "GEMINI_API_KEY", "models": ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3-flash-preview"]},
]

# ------------------------------------------------------------------ schedule
PUBLISH_HOUR_NY = 6        # 06:30 New York
PUBLISH_MINUTE_NY = 30
UA = "Mozilla/5.0 (compatible; EconomicBearings-Analyst/1.0)"
