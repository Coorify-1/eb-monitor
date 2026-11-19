/**
 * EB Signals — daily trend snapshot for the EB Investment Dashboard
 * Cloudflare Worker (free plan). Runs once a day at 10:00 PM New York time.
 *
 * SOURCES (legal version — same structure, same output)
 *  - ETFs (32): Twelve Data. Public display needs a Twelve Data BUSINESS plan
 *    (Venture) or their free non-profit programme: put that key in TWELVE_KEY.
 *  - Currencies (EUR/USD, GBP/USD, USD/JPY, USD/CHF, USD/CNY): European Central Bank
 *    reference rates (ECB Data Portal, free, reuse with attribution).
 *  - USD/RUB: Bank of Russia official rate (the ECB stopped its rouble rate in March 2022).
 *  - Crypto (BTC, ETH): CoinGecko Demo API (free, attribution "Data provided by CoinGecko").
 *  - Equity markets (11 countries): OECD share price indices via FRED (monthly, free,
 *    OECD data under CC BY 4.0). Used instead of the ETFs when no licensed key is set.
 *  - Stock analysis: Finnhub ONLY with Finnhub's written approval (empty key = section skipped).
 *  - Yields: U.S. Treasury, ECB, Bank of England, OECD via FRED (official, free).
 *    China (ChinaBond page) is OFF by default: no reuse licence for its data.
 *
 * WHAT IT DOES
 *  - Downloads ~5 years of daily closes for 32 ETFs (Twelve Data), 4 FX pairs (ECB)
 *    and 2 cryptos (CoinGecko, 1 year).
 *  - Adds gold, silver, platinum, copper from your Metals Worker (?history=…)
 *    and Brent, WTI, Henry Hub gas from the U.S. EIA daily spot prices (via FRED CSV,
 *    public domain, no key). The old CEII crude.json endpoint no longer exists.
 *  - Computes returns (1D … 1Y, YTD), 50/200-day averages, 52-week high/low,
 *    volatility, a 0–100 trend score and plain-English signals.
 *  - Stores ONE JSON snapshot in KV. The dashboard reads it with GET /signals.
 *
 * TWO WAYS TO INSTALL
 *  A) Inside your existing market-proxy Worker (recommended, same Twelve Data key):
 *       import { handleSignals, runSignals } from "./eb-signals-worker.js"
 *       // in fetch():   if (new URL(request.url).pathname.startsWith("/signals"))
 *       //                   return handleSignals(request, env)
 *       // add:          async scheduled(event, env, ctx) { ctx.waitUntil(runSignals(env)) }
 *  B) As its own Worker: deploy this file as is (it has a default export).
 *
 * SETTINGS (Worker → Settings)
 *  - KV namespace binding   EB_SIGNALS            (required)
 *  - Secret                 TWELVE_KEY            (optional: built-in key below is used if empty)
 *  - Variable               METALS_URL            (optional: built-in address below)
 *  - Secret                 RUN_TOKEN             (required for /signals/run, /signals/check …)
 *  - Variable               ALLOWED_ORIGINS       (optional, comma list; empty = everyone)
 *  - Cron triggers          * /10 * * * *         (write it without the space after *)
 *    Every 10 minutes, all day. Each tick first checks (1 KV read) whether the
 *    snapshot already covers the last weekday whose 10 PM New York has passed.
 *    If yes it stops at once; if not it does one more step. So the job starts at
 *    10 PM New York and, when a step fails, simply goes on at the next tick
 *    instead of losing the whole night. Weekends are skipped (Friday is kept).
 *
 * DAILY CHECK (alert only when something is wrong; nothing is recalculated):
 *  - Variable  ALERT_WEBHOOK   where to send the alert: an ntfy.sh topic URL (free phone
 *                              notifications, e.g. https://ntfy.sh/eb-signals-xyz), a Discord
 *                              or a Slack webhook URL. Empty = no alert (the check still shows
 *                              in /signals/health).
 *  - Variable  ALERT_HOUR      local hour of the check (default 8)
 *  - Variable  ALERT_TZ        time zone (default Europe/Paris)
 *  - Variable  ALERT_IGNORE    assets never reported as missing, comma list (default Russia)
 *    GET /signals/check?token=RUN_TOKEN          → runs the check now
 *    GET /signals/check?token=RUN_TOKEN&test=1   → also sends a test message when all is fine
 *
 * MANUAL RUN (first install, or to test):
 *    GET /signals/run?token=RUN_TOKEN   → runs one step (call it ~6 times, 1 min apart)
 *
 * SETUP CHECK:
 *    GET /signals/health                → lists anything missing in the settings
 */

/* ---- Built-in settings (used when the Worker settings are empty) ---- */
// The Worker code runs on Cloudflare only: visitors never see this key.
const DEFAULT_TWELVE_KEY = "" // not used: ETFs are off (no Twelve Data)
const DEFAULT_METALS_URL = "https://metals.b-boussoffara.workers.dev/"
const DEFAULT_RUN_TOKEN = "" // set the Secret RUN_TOKEN in Cloudflare (never in this file)
// Finnhub key for the stock analysis. Finnhub plans are personal use only: leave EMPTY
// until Finnhub gives written approval for display on your site (empty = section skipped).
// You can also set it as a Secret named FINNHUB_KEY in the Worker settings.
const DEFAULT_FINNHUB_KEY = ""
// CoinGecko Demo key (free) for the crypto history
const DEFAULT_COINGECKO_KEY = "" // set the Secret COINGECKO_KEY in Cloudflare (works without, lower limits)
// China 10-year yield from the ChinaBond page: no reuse licence -> off
const CHINA_ENABLED = false
// ETFs (Twelve Data): set to true ONLY with a Twelve Data BUSINESS key (Venture) or
// their non-profit plan. false = ETFs are not downloaded and their panels are hidden.
// (Can also be set with a Worker variable TWELVE_LICENSED = "true".)
const TWELVE_LICENSED = false

/** Worker settings win; otherwise the built-in values above. */
function withDefaults(env) {
    return {
        ...env,
        TWELVE_KEY: (env && env.TWELVE_KEY) || DEFAULT_TWELVE_KEY,
        METALS_URL: (env && env.METALS_URL) || DEFAULT_METALS_URL,
        RUN_TOKEN: (env && env.RUN_TOKEN) || DEFAULT_RUN_TOKEN,
        FINNHUB_KEY: (env && env.FINNHUB_KEY) || DEFAULT_FINNHUB_KEY,
        COINGECKO_KEY: (env && env.COINGECKO_KEY) || DEFAULT_COINGECKO_KEY,
        TWELVE_LICENSED: TWELVE_LICENSED || String((env && env.TWELVE_LICENSED) || "") === "true",
    }
}

const STATE_VERSION = 3 // bump when the stored data format changes
const RUN_HOUR_NY = 22
const BATCH = 8 // Twelve Data free plan: 8 symbols per minute

// id | Twelve Data symbol | name | class
export const UNIVERSE = [
    ["SPY", "SPY", "S&P 500", "US Equities"],
    ["QQQ", "QQQ", "Nasdaq 100", "US Equities"],
    ["DIA", "DIA", "Dow Jones", "US Equities"],
    ["IWM", "IWM", "Russell 2000", "US Equities"],
    ["VIXY", "VIXY", "Volatility (VIX futures)", "US Equities"],
    ["XLE", "XLE", "Energy", "Sectors"],
    ["XLB", "XLB", "Materials", "Sectors"],
    ["XLY", "XLY", "Cons. Discretionary", "Sectors"],
    ["XLI", "XLI", "Industrials", "Sectors"],
    ["XLK", "XLK", "Technology", "Sectors"],
    ["XLF", "XLF", "Financials", "Sectors"],
    ["XLP", "XLP", "Cons. Staples", "Sectors"],
    ["XLU", "XLU", "Utilities", "Sectors"],
    ["XLC", "XLC", "Communications", "Sectors"],
    ["XLV", "XLV", "Health Care", "Sectors"],
    ["XLRE", "XLRE", "Real Estate", "Sectors"],
    ["EFA", "EFA", "Developed ex-US", "Global"],
    ["EEM", "EEM", "Emerging", "Global"],
    ["VGK", "VGK", "Europe", "Global"],
    ["EWJ", "EWJ", "Japan", "Global"],
    ["EWU", "EWU", "United Kingdom", "Global"],
    ["EWQ", "EWQ", "France", "Global"],
    ["EWG", "EWG", "Germany", "Global"],
    ["EWZ", "EWZ", "Brazil", "Global"],
    ["INDA", "INDA", "India", "Global"],
    ["MCHI", "MCHI", "China", "Global"],
    ["SHY", "SHY", "Treasuries 1–3Y", "Bonds"],
    ["IEF", "IEF", "Treasuries 7–10Y", "Bonds"],
    ["TLT", "TLT", "Treasuries 20Y+", "Bonds"],
    ["TIP", "TIP", "TIPS", "Bonds"],
    ["LQD", "LQD", "Investment Grade", "Bonds"],
    ["HYG", "HYG", "High Yield", "Bonds"],
    ["EURUSD", "EUR/USD", "Euro", "Currencies"],
    ["GBPUSD", "GBP/USD", "British Pound", "Currencies"],
    ["USDJPY", "USD/JPY", "Japanese Yen", "Currencies"],
    ["USDCHF", "USD/CHF", "Swiss Franc", "Currencies"],
    ["USDCNY", "USD/CNY", "Chinese Yuan", "Currencies"],
    ["USDRUB", "USD/RUB", "Russian Ruble", "Currencies"],
    ["BTC", "BTC/USD", "Bitcoin", "Crypto"],
    ["ETH", "ETH/USD", "Ethereum", "Crypto"],
    // OECD share price indices (broad national markets, monthly averages, local currency) via FRED
    ["eq_US", "SPASTT01USM661N", "United States", "Equity Markets"],
    ["eq_JP", "SPASTT01JPM661N", "Japan", "Equity Markets"],
    ["eq_DE", "SPASTT01DEM661N", "Germany", "Equity Markets"],
    ["eq_GB", "SPASTT01GBM661N", "United Kingdom", "Equity Markets"],
    ["eq_FR", "SPASTT01FRM661N", "France", "Equity Markets"],
    ["eq_CN", "SPASTT01CNM661N", "China", "Equity Markets"],
    ["eq_IN", "SPASTT01INM661N", "India", "Equity Markets"],
    ["eq_BR", "SPASTT01BRM661N", "Brazil", "Equity Markets"],
    ["eq_KR", "SPASTT01KRM661N", "Korea", "Equity Markets"],
    ["eq_CA", "SPASTT01CAM661N", "Canada", "Equity Markets"],
    ["eq_AU", "SPASTT01AUM661N", "Australia", "Equity Markets"],
    // Russia: the OECD series has repeated the same value since 2025 -> skipped automatically
    // (see fetchFredMonthly) until real data comes back
    ["eq_RU", "SPASTT01RUM661N", "Russia", "Equity Markets"],
].map(([id, td, name, cls]) => ({
    id,
    td,
    name,
    cls,
    // where the history comes from: ECB for currencies, CoinGecko for crypto, FRED (monthly)
    // for the OECD equity indices, Twelve Data for ETFs
    src:
        id === "USDRUB"
            ? "cbr"
            : cls === "Currencies"
            ? "ecb"
            : cls === "Crypto"
              ? "coingecko"
              : cls === "Equity Markets"
                ? "fredm"
                : "twelve",
}))
const COINGECKO_ID = { BTC: "bitcoin", ETH: "ethereum" }
/** The assets this Worker may download and publish (ETFs only with a licensed key). */
const activeUniverse = (env) => UNIVERSE.filter((a) => a.src !== "twelve" || env.TWELVE_LICENSED)

const METALS = [
    ["gold", "Gold"],
    ["silver", "Silver"],
    ["platinum", "Platinum"],
    ["copper", "Copper"],
]
/* Stock analysis universe: global leaders listed in the U.S. (Finnhub free plan = U.S. listings).
   ticker | display name | country (ISO) . Add or remove freely (keep it under ~60). */
export const STOCKS = [
    ["NVDA", "NVIDIA", "US"], ["MSFT", "Microsoft", "US"], ["AAPL", "Apple", "US"], ["GOOGL", "Alphabet", "US"],
    ["AMZN", "Amazon", "US"], ["META", "Meta Platforms", "US"], ["AVGO", "Broadcom", "US"], ["TSLA", "Tesla", "US"],
    ["LLY", "Eli Lilly", "US"], ["JPM", "JPMorgan Chase", "US"], ["V", "Visa", "US"], ["MA", "Mastercard", "US"],
    ["UNH", "UnitedHealth", "US"], ["COST", "Costco", "US"], ["NFLX", "Netflix", "US"], ["ORCL", "Oracle", "US"],
    ["AMD", "AMD", "US"], ["CRM", "Salesforce", "US"], ["ADBE", "Adobe", "US"], ["XOM", "ExxonMobil", "US"],
    ["JNJ", "Johnson & Johnson", "US"], ["PG", "Procter & Gamble", "US"], ["KO", "Coca-Cola", "US"], ["WMT", "Walmart", "US"],
    ["HD", "Home Depot", "US"], ["ISRG", "Intuitive Surgical", "US"], ["NOW", "ServiceNow", "US"], ["UBER", "Uber", "US"],
    ["TSM", "TSMC", "TW"], ["ASML", "ASML", "NL"], ["SAP", "SAP", "DE"], ["NVO", "Novo Nordisk", "DK"],
    ["TM", "Toyota", "JP"], ["SONY", "Sony", "JP"], ["AZN", "AstraZeneca", "GB"], ["SHEL", "Shell", "GB"],
    ["BABA", "Alibaba", "CN"], ["PDD", "PDD Holdings", "CN"], ["MELI", "MercadoLibre", "AR"], ["BMWYY", "BMW", "DE"],
    ["NSRGY", "Nestlé", "CH"], ["LVMUY", "LVMH", "FR"], ["SIEGY", "Siemens", "DE"], ["TTE", "TotalEnergies", "FR"],
    ["RACE", "Ferrari", "IT"], ["HSBC", "HSBC", "GB"], ["UL", "Unilever", "GB"], ["SNY", "Sanofi", "FR"], ["DEO", "Diageo", "GB"],
].map(([ticker, name, country]) => ({ ticker, name, country }))
const STOCK_BATCH = 10 // 4 Finnhub calls each → 40 requests per run (free Workers limit: 50)

/* ---------- EB Stock Analysis: metrics + 7-pillar scoring (shared by Worker and component) ---------- */

const SK = {
    pe: ["peTTM", "peBasicExclExtraTTM", "peExclExtraTTM", "peNormalizedAnnual"],
    peg: ["pegTTM", "pegRatio"],
    evEbitda: ["evEbitdaTTM", "currentEv/ebitdaTTM", "evEbitdaAnnual"],
    revG1: ["revenueGrowthTTMYoy", "revenueGrowthQuarterlyYoy"],
    revG3: ["revenueGrowth3Y"],
    revG5: ["revenueGrowth5Y"],
    epsG1: ["epsGrowthTTMYoy", "epsGrowthQuarterlyYoy"],
    epsG5: ["epsGrowth5Y", "epsGrowth3Y"],
    grossMargin: ["grossMarginTTM", "grossMarginAnnual"],
    opMargin: ["operatingMarginTTM", "operatingMarginAnnual"],
    netMargin: ["netProfitMarginTTM", "netProfitMarginAnnual"],
    roe: ["roeTTM", "roeRfy"],
    roic: ["roiTTM", "roiAnnual"],
    de: ["totalDebt/totalEquityQuarterly", "totalDebt/totalEquityAnnual", "longTermDebt/equityQuarterly"],
    currentRatio: ["currentRatioQuarterly", "currentRatioAnnual"],
    pfcf: ["pfcfShareTTM", "pfcfShareAnnual", "currentEv/freeCashFlowTTM"],
    r1m: ["monthToDatePriceReturnDaily", "4WeekPriceReturnDaily"],
    r3m: ["13WeekPriceReturnDaily"],
    r6m: ["26WeekPriceReturnDaily"],
    r12m: ["52WeekPriceReturnDaily"],
    mcap: ["marketCapitalization"],
    beta: ["beta"],
}
const SK_KEYS = Object.values(SK).flat()

const finite = (v) => typeof v === "number" && isFinite(v)

/** Picks our fields from a Finnhub /stock/metric "metric" object. */
function extractMetrics(m) {
    const o = {}
    for (const [k, keys] of Object.entries(SK)) {
        o[k] = null
        for (const key of keys)
            if (m && finite(m[key])) {
                o[k] = m[key]
                break
            }
    }
    // PEG = P/E ÷ EPS growth when not given
    if (!finite(o.peg) && finite(o.pe) && o.pe > 0 && finite(o.epsG5) && o.epsG5 > 0) o.peg = o.pe / o.epsG5
    o.fcfYield = finite(o.pfcf) && o.pfcf > 0 ? 100 / o.pfcf : null
    return o
}

const median = (xs) => {
    const a = xs.filter(finite).sort((x, y) => x - y)
    if (!a.length) return null
    const i = Math.floor(a.length / 2)
    return a.length % 2 ? a[i] : (a[i - 1] + a[i]) / 2
}

/** Share of the universe this value beats (0..1). lowerBetter flips it. Missing = null. */
function rankIn(all, v, lowerBetter, invalidIfNonPositive) {
    if (!finite(v)) return null
    if (invalidIfNonPositive && v <= 0) return 0 // negative P/E etc. = worst
    const xs = all.filter((x) => finite(x) && (!invalidIfNonPositive || x > 0))
    if (xs.length < 3) return null
    const below = xs.filter((x) => (lowerBetter ? x > v : x < v)).length
    const ties = xs.filter((x) => x === v).length - 1 // equal values share the middle
    return (below + Math.max(0, ties) / 2) / (xs.length - 1)
}
const avg10 = (parts) => {
    const xs = parts.filter(finite)
    return xs.length ? Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 100) / 10 : null
}

/** Consensus from Finnhub recommendation counts: -2 (strong sell) … +2 (strong buy). */
function consensus(r) {
    if (!r) return null
    const sb = r.strongBuy || 0, b = r.buy || 0, h = r.hold || 0, s = r.sell || 0, ss = r.strongSell || 0
    const n = sb + b + h + s + ss
    return n ? (2 * sb + b - s - 2 * ss) / n : null
}


/* ---------- 8. Negative News: keyword reading of the last 14 days of headlines ---------- */
const NEG_WORDS = ["lawsuit","sued","sues","probe","investigation","investigating","fraud","recall","recalls","downgrade","downgraded","downgrades","cut","cuts","miss","misses","missed","plunge","plunges","plunged","slump","slumps","tumble","tumbles","sink","sinks","drop","drops","falls","fell","decline","declines","layoff","layoffs","fine","fined","penalty","antitrust","ban","banned","sanction","sanctions","warning","warns","loss","losses","bankruptcy","default","scandal","resign","resigns","resignation","strike","delay","delays","delayed","halt","halts","outage","breach","hack","hacked","subpoena","tariff","tariffs","crash","weak","weaker","concern","concerns","slowdown","bearish","selloff","sell-off","accused","accuses","restatement","underperform","lowers","lowered","shortfall","disappoint","disappoints","disappointing","lawsuits","violation","violations","fire","explosion","glitch","worst","headwinds","struggle","struggles","espionage","spy","spying","spies","resigned","ousted","departure","exits","charged","indicted","arrest","arrested","raid","raided","smuggling","leak","leaked","scrutiny","crackdown","blacklist","blacklisted","blocked","probes","investigated","allegations","alleged","illegal","guilty","settlement","plummets","plummet","tanks","slides","sell","selling","turmoil","chaos","crisis","threat","threatens","risks","fears","fear","worries","worry","uncertainty","controversy","backlash","boycott"]
const POS_WORDS = ["beat","beats","surge","surges","surged","soar","soars","rally","rallies","record","upgrade","upgraded","upgrades","raises","raised","strong","stronger","wins","win","approval","approved","launch","launches","partnership","deal","buyback","dividend","outperform","bullish","jumps","jumped","gains","profit","profits","expands","expansion","breakthrough","boost","boosts","tops","best","growth","climbs","rebound","rebounds"]
const NEG_SET = new Set(NEG_WORDS)
const POS_SET = new Set(POS_WORDS)
// Serious events: weigh double and cap the pillar (see scoreStocks)
const SEVERE_WORDS = ["fraud","espionage","spying","spy","indicted","charged","arrested","arrest","resigns","resigned","resignation","ousted","bankruptcy","scandal","subpoena","raid","raided","smuggling","sanctions","guilty","illegal"]
const SEVERE_PHRASES = ["steps down","step down","stepping down","class action","export controls","national security","short seller","under investigation","accounting irregularities"]
const NEG_PHRASES = ["steps down","step down","stepping down","class action","export controls","short seller","under investigation","guidance cut","profit warning"]
const SEVERE_SET = new Set(SEVERE_WORDS)


function newsStats(items) {
    const list = (Array.isArray(items) ? items : []).filter((x) => x && x.headline).slice(0, 100)
    let neg = 0
    let pos = 0
    let tone = 0
    let severe = 0
    const negatives = []
    for (const x of list) {
        const text = (String(x.headline) + " " + String(x.summary || "").slice(0, 300)).toLowerCase()
        const words = text.match(/[a-z][a-z-]+/g) || []
        let n = 0
        let p = 0
        let sev = false
        for (const w of words) {
            if (SEVERE_SET.has(w)) (n += 2), (sev = true)
            else if (NEG_SET.has(w)) n++
            else if (POS_SET.has(w)) p++
        }
        for (const ph of NEG_PHRASES) if (text.includes(ph)) n += 2
        for (const ph of SEVERE_PHRASES) if (text.includes(ph)) sev = true
        tone += (p - n) / Math.max(1, p + n)
        if (n > p) {
            neg++
            if (sev) severe++
            negatives.push({ h: String(x.headline).slice(0, 160), u: x.url || "", s: x.source || "", t: x.datetime || 0, w: n - p + (sev ? 10 : 0), sev })
        } else if (p > n) pos++
    }
    negatives.sort((a, b) => b.w - a.w || b.t - a.t)
    return {
        n: list.length,
        neg,
        pos,
        severe,
        negShare: list.length ? (neg / list.length) * 100 : null,
        tone: list.length ? tone / list.length : null,
        top: negatives.slice(0, 3).map(({ w, ...r }) => r),
    }
}

const PILLARS = [
    ["valuation", "Valuation"],
    ["growth", "Revenue Growth"],
    ["profitability", "Profitability"],
    ["health", "Financial Health"],
    ["moat", "Competitive Advantage"],
    ["momentum", "Market Momentum"],
    ["outlook", "Future Outlook"],
    ["news", "Negative News"],
]

/**
 * stocks: [{ ticker, m: metrics, rec }] → adds pillars (0–10) and score (0–100).
 * Each pillar ranks the stock against the whole universe.
 */
function scoreStocks(stocks) {
    const col = (k) => stocks.map((s) => s.m[k])
    const C = {}
    for (const k of Object.keys(SK).concat(["fcfYield"])) C[k] = col(k)
    const cons = stocks.map((s) => consensus(s.rec))
    const negShares = stocks.map((s) => (s.news && s.news.n >= 1 ? s.news.negShare : null))
    const tones = stocks.map((s) => (s.news && s.news.n >= 1 ? s.news.tone : null))
    for (const [i, s] of stocks.entries()) {
        const m = s.m
        const allPos = [m.revG1, m.revG3, m.revG5].filter(finite)
        const steady = allPos.length >= 2 ? (allPos.every((x) => x > 0) ? 1 : allPos.some((x) => x > 0) ? 0.5 : 0) : null
        const p = {
            valuation: avg10([
                rankIn(C.pe, m.pe, true, true),
                rankIn(C.peg, m.peg, true, true),
                rankIn(C.evEbitda, m.evEbitda, true, true),
            ]),
            growth: avg10([rankIn(C.revG1, m.revG1), rankIn(C.revG3, m.revG3), rankIn(C.revG5, m.revG5), steady]),
            profitability: avg10([
                rankIn(C.netMargin, m.netMargin),
                rankIn(C.roe, m.roe),
                rankIn(C.roic, m.roic),
                rankIn(C.epsG1, m.epsG1),
            ]),
            health: avg10([
                rankIn(C.de, m.de, true),
                rankIn(C.currentRatio, m.currentRatio),
                rankIn(C.fcfYield, m.fcfYield),
            ]),
            // automatic proxy for a moat: pricing power (gross margin), returns on capital, scale
            moat: avg10([rankIn(C.grossMargin, m.grossMargin), rankIn(C.roic, m.roic), rankIn(C.mcap, m.mcap)]),
            momentum: avg10([rankIn(C.r1m, m.r1m), rankIn(C.r3m, m.r3m), rankIn(C.r6m, m.r6m), rankIn(C.r12m, m.r12m)]),
            outlook: avg10([rankIn(cons, cons[i]), rankIn(C.epsG5, m.epsG5)]),
            // 10 = little negative news compared with the other companies
            news: avg10([rankIn(negShares, negShares[i], true), rankIn(tones, tones[i])]),
        }
        // serious events (fraud, espionage, CEO exit, charges…): 2+ headlines cap at 2/10, 1 headline at 4/10
        const sev = (s.news && s.news.severe) || 0
        if (finite(p.news) && sev >= 2) p.news = Math.min(p.news, 2)
        else if (finite(p.news) && sev === 1) p.news = Math.min(p.news, 4)
        if (!finite(p.news) && sev >= 1) p.news = sev >= 2 ? 1 : 3
        s.pillars = p
        s.consensus = cons[i]
        s.score = ebScore(p)
    }
    return stocks
}

function ebScore(p) {
    const xs = PILLARS.map(([k]) => p[k]).filter(finite)
    return xs.length >= 6 ? Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) : null
}

function stockMedians(stocks) {
    const o = {}
    for (const k of Object.keys(SK).concat(["fcfYield"])) o[k] = median(stocks.map((s) => s.m[k]))
    return o
}


/* ------------------------------------------------------------------ */
/* Global yields (government bonds) — free official sources            */
/*  - FRED CSV (no key): U.S. Treasuries daily, OECD 10-year monthly   */
/*  - ECB Data Portal: euro area AAA curve daily (2Y, 10Y)             */
/* ------------------------------------------------------------------ */

const UA = { "User-Agent": "Mozilla/5.0 (compatible; EB-Signals/1.0; +https://economic-bearings)" , Accept: "text/csv,application/xml,*/*" }

// euro-area countries: ECB monthly long-term (10-year) government bond yields (Maastricht criterion)
const YIELD_ECB = [
    ["Germany", "DE"],
    ["France", "FR"],
    ["Italy", "IT"],
    ["Spain", "ES"],
    ["Netherlands", "NL"],
    ["Portugal", "PT"],
    ["Greece", "GR"],
]
// other countries: FRED (OECD monthly) as a last resort — FRED may refuse Cloudflare servers
const YIELD_FRED = [
    ["Japan", "JP", "IRLTLT01JPM156N"],
    ["Switzerland", "CH", "IRLTLT01CHM156N"],
    ["Canada", "CA", "IRLTLT01CAM156N"],
    ["Australia", "AU", "IRLTLT01AUM156N"],
]
let yieldsProblems = []

const toIso = (d) => {
    const s = String(d).trim()
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10)
    if (/^\d{4}-\d{2}$/.test(s)) return s + "-01"
    const t = Date.parse(s.replace(/-/g, " "))
    return isNaN(t) ? null : new Date(t - new Date(t).getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}
const splitCsv = (line) => line.split(",").map((c) => c.replace(/^"|"$/g, "").trim())

/** CSV text → { header, rows } */
function parseCsvText(text) {
    const lines = String(text || "").split(/\r?\n/).filter((l) => l.trim())
    return { header: lines.length ? splitCsv(lines[0]) : [], rows: lines.slice(1).map(splitCsv) }
}
const sortPts = (pts) => pts.filter((p) => p[0] && isNum(p[1])).sort((a, b) => (a[0] < b[0] ? -1 : 1))

/** U.S. Treasury daily par yield curve (this year + last year). */
async function treasuryCurve() {
    const y = new Date().getUTCFullYear()
    const out = { y2: [], y5: [], y10: [], y30: [] }
    for (const year of [y - 1, y]) {
        const url = `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/${year}/all?type=daily_treasury_yield_curve&field_tdr_date_value=${year}&page&_format=csv`
        const r = await fetch(url, { headers: UA })
        if (!r.ok) throw new Error(`U.S. Treasury ${year}: HTTP ${r.status}`)
        const { header, rows } = parseCsvText(await r.text())
        const col = (name) => header.findIndex((h) => h.toLowerCase() === name.toLowerCase())
        const ix = { d: col("Date"), y2: col("2 Yr"), y5: col("5 Yr"), y10: col("10 Yr"), y30: col("30 Yr") }
        if (ix.d < 0 || ix.y10 < 0) throw new Error("U.S. Treasury: unexpected CSV columns")
        for (const c of rows) {
            const d = toIso(c[ix.d])
            for (const k of ["y2", "y5", "y10", "y30"]) {
                const v = ix[k] >= 0 && c[ix[k]] !== "" ? Number(c[ix[k]]) : NaN
                if (d && isNum(v)) out[k].push([d, v])
            }
        }
    }
    for (const k of Object.keys(out)) out[k] = sortPts(out[k])
    if (!out.y10.length) throw new Error("U.S. Treasury: no data")
    return out
}

/** ECB Data Portal series → [[date, value]] */
async function ecbSeries(flow, key, n) {
    const r = await fetch(`https://data-api.ecb.europa.eu/service/data/${flow}/${key}?format=csvdata&lastNObservations=${n}`, { headers: UA })
    if (!r.ok) throw new Error(`ECB ${flow}/${key}: HTTP ${r.status}`)
    const { header, rows } = parseCsvText(await r.text())
    const di = header.indexOf("TIME_PERIOD")
    const vi = header.indexOf("OBS_VALUE")
    return sortPts(rows.map((c) => [toIso(c[di]), c[vi] === "" ? NaN : Number(c[vi])]))
}

/** Bank of England 10-year nominal par yield, daily. */
async function boe10y() {
    const from = new Date(Date.now() - 400 * 864e5)
    const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][from.getUTCMonth()]
    const df = `${String(from.getUTCDate()).padStart(2, "0")}/${m}/${from.getUTCFullYear()}`
    const url = `https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=${df}&Dateto=now&SeriesCodes=IUDMNPY&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N`
    const r = await fetch(url, { headers: UA })
    if (!r.ok) throw new Error(`Bank of England: HTTP ${r.status}`)
    const { rows } = parseCsvText(await r.text())
    const pts = sortPts(rows.map((c) => [toIso(c[0]), Number(c[c.length - 1])]))
    if (!pts.length) throw new Error("Bank of England: no data")
    return pts
}

async function fredSeries(id, since) {
    const r = await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${id}&cosd=${since}`, { headers: UA })
    if (!r.ok) throw new Error(`FRED ${id}: HTTP ${r.status}`)
    const { rows } = parseCsvText(await r.text())
    return sortPts(rows.map((c) => [toIso(c[0]), c[c.length - 1] === "" ? NaN : Number(c[c.length - 1])]))
}

/** China: MOF government bond yield curve page (one request a night). History is built up in KV. */
async function chinaMof(env) {
    const url = "https://yield.chinabond.com.cn/cbweb-czb-web/czb/moreInfo?locale=en_US&nameType=1"
    const r = await fetch(url, { headers: { ...UA, Accept: "text/html" } })
    if (!r.ok) throw new Error(`China MOF: HTTP ${r.status}`)
    const text = (await r.text()).replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ")
    const date = (text.match(/(\d{4}-\d{2}-\d{2})\s+3Mo/) || text.match(/(\d{4}-\d{2}-\d{2})/) || [])[1]
    const num = "(-?\\d+(?:\\.\\d+)?)"
    const row = (tenor) => {
        const m = text.match(new RegExp(tenor + "\\s+" + num + "\\s+" + num + "\\s+" + num + "\\s+" + num))
        return m ? { y: +m[1], d1: +m[2], m1: +m[3], y1: +m[4] } : null
    }
    const t10 = row("10Yr")
    const t2 = row("2Yr")
    if (!date || !t10) throw new Error("China MOF: table not found")
    // keep a nightly history (max ~400 days) for the chart
    let hist = []
    if (env && env.EB_SIGNALS) {
        try {
            hist = JSON.parse((await env.EB_SIGNALS.get("y:CN")) || "[]")
        } catch {}
        if (!hist.length || hist[hist.length - 1][0] !== date) hist.push([date, t10.y])
        hist = hist.filter((q) => Date.parse(q[0]) >= Date.parse(date) - 400 * 864e5)
        await env.EB_SIGNALS.put("y:CN", JSON.stringify(hist))
    }
    // anchor points rebuilt from the page's own changes (1 year, 1 month, 1 day ago), so the chart works from day one
    const ago = (days) => new Date(Date.parse(date) - days * 864e5).toISOString().slice(0, 10)
    const r3 = (v) => Math.round(v * 1000) / 1000
    const anchors = [
        [ago(365), r3(t10.y - t10.y1 / 100)],
        [ago(30), r3(t10.y - t10.m1 / 100)],
        [ago(1), r3(t10.y - t10.d1 / 100)],
    ]
    const known = new Set(hist.map((q) => q[0]))
    const firstReal = hist.length ? hist[0][0] : date
    const merged = [...anchors.filter((q) => !known.has(q[0]) && q[0] < firstReal), ...hist]
    if (!merged.some((q) => q[0] === date)) merged.push([date, t10.y])
    merged.sort((x, y) => (x[0] < y[0] ? -1 : 1))
    return { date, y10: t10.y, y2: t2 ? t2.y : null, chg1m: Math.round(t10.m1), chg1y: Math.round(t10.y1), hist: merged }
}

/** Value about `days` before the last point (for changes). */
function valueAgo(pts, days) {
    if (!pts || !pts.length) return null
    const last = Date.parse(pts[pts.length - 1][0])
    for (let i = pts.length - 1; i >= 0; i--) if (Date.parse(pts[i][0]) <= last - days * 864e5) return pts[i][1]
    return null
}
const bp = (a, b) => (isNum(a) && isNum(b) ? Math.round((a - b) * 100) : null)
const lastPt = (pts) => (pts && pts.length ? pts[pts.length - 1] : null)

async function fetchYields(env) {
    yieldsProblems = []
    const safe = (p) =>
        p.catch((e) => {
            yieldsProblems.push(String((e && e.message) || e))
            return null
        })
    const sinceMonthly = new Date(Date.now() - 800 * 864e5).toISOString().slice(0, 10)

    const [us, ea2, ea10, uk, ecbRows, fredRows, cn] = await Promise.all([
        safe(treasuryCurve()),
        safe(ecbSeries("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y", 300)),
        safe(ecbSeries("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", 300)),
        safe(boe10y()),
        Promise.all(YIELD_ECB.map(([, cc]) => safe(ecbSeries("IRS", `M.${cc}.L.L40.CI.0000.EUR.N.Z`, 26)))),
        Promise.all(YIELD_FRED.map(([, , id]) => safe(fredSeries(id, sinceMonthly)))),
        CHINA_ENABLED ? safe(chinaMof(env)) : Promise.resolve(null),
    ])

    const rows = []
    const row = (country, cc, freq, pts10, pts2) => {
        const l = lastPt(pts10)
        if (!l) return
        // one year of history for the chart (daily series: one point a week)
        const cut = Date.parse(l[0]) - 372 * 864e5
        const year = pts10.filter((q) => Date.parse(q[0]) >= cut)
        const hist = (freq === "daily" ? year.filter((_, i, arr) => (arr.length - 1 - i) % 5 === 0) : year).map((q) => [q[0], Math.round(q[1] * 1000) / 1000])
        rows.push({
            country,
            cc,
            freq,
            hist,
            date: l[0],
            y2: lastPt(pts2)?.[1] ?? null,
            y10: l[1],
            chg1m: bp(l[1], valueAgo(pts10, freq === "daily" ? 30 : 28)),
            chg1y: bp(l[1], valueAgo(pts10, freq === "daily" ? 365 : 360)),
        })
    }
    if (us) row("United States", "US", "daily", us.y10, us.y2)
    row("Euro area (AAA)", "EU", "daily", ea10, ea2)
    YIELD_ECB.forEach(([country, cc], i) => row(country, cc, "monthly", ecbRows[i], null))
    if (uk) row("United Kingdom", "GB", "daily", uk, null)
    else {
        // Bank of England down: OECD monthly 10-year yield for the UK (via FRED) instead
        const ukm = await safe(fredSeries("IRLTLT01GBM156N", sinceMonthly))
        row("United Kingdom", "GB", "monthly", ukm, null)
    }
    YIELD_FRED.forEach(([country, cc], i) => row(country, cc, "monthly", fredRows[i], null))
    if (cn)
        rows.push({
            country: "China",
            cc: "CN",
            freq: "daily",
            date: cn.date,
            y2: cn.y2,
            y10: cn.y10,
            chg1m: cn.chg1m,
            chg1y: cn.chg1y,
            hist: cn.hist.length > 1 ? cn.hist : [],
        })

    // a source that failed this time (e.g. Bank of England HTTP 500): keep the country's last
    // known row from the previous snapshot, marked stale, instead of dropping it
    let prevYields = null
    if (env && env.EB_SIGNALS) {
        try {
            const prev = JSON.parse((await env.EB_SIGNALS.get("signals:latest")) || "null")
            prevYields = (prev && prev.yields) || null
        } catch {}
    }
    for (const r of (prevYields && prevYields.rows) || [])
        if (r && r.cc && !rows.some((x) => x.cc === r.cc)) rows.push({ ...r, stale: true })
    // same display order every night
    const ORDER = ["US", "EU", ...YIELD_ECB.map((x) => x[1]), "GB", ...YIELD_FRED.map((x) => x[1]), "CN"]
    rows.sort((a, b) => ORDER.indexOf(a.cc) - ORDER.indexOf(b.cc))

    // gap with Germany (Germany's latest monthly value)
    const de = rows.find((r) => r.cc === "DE")
    rows.forEach((r) => (r.spreadDE = de && r.cc !== "DE" ? bp(r.y10, de.y10) : null))

    let curve =
        us && lastPt(us.y10) && lastPt(us.y2)
            ? {
                  y2: lastPt(us.y2)[1],
                  y5: lastPt(us.y5)?.[1] ?? null,
                  y10: lastPt(us.y10)[1],
                  y30: lastPt(us.y30)?.[1] ?? null,
                  slope: bp(lastPt(us.y10)[1], lastPt(us.y2)[1]),
                  slope1y: bp(valueAgo(us.y10, 365), valueAgo(us.y2, 365)),
                  hist: (() => {
                      const m2 = new Map(us.y2.map((q) => [q[0], q[1]]))
                      return us.y10
                          .filter((q) => m2.has(q[0]))
                          .filter((_, i, arr) => (arr.length - 1 - i) % 5 === 0)
                          .map((q) => [q[0], Math.round((q[1] - m2.get(q[0])) * 100)])
                  })(),
              }
            : null
    if (!curve && prevYields && prevYields.curve) curve = { ...prevYields.curve, stale: true }
    return { rows, curve, problem: yieldsProblems.length ? yieldsProblems.join(" · ") : undefined }
}

// U.S. EIA daily spot prices, read from FRED (public domain). Published with a few days' delay.
/** Risk gauges for Market Mood (U.S. Federal Reserve, weekly, free):
    Chicago Fed NFCI credit subindex and St. Louis Fed Financial Stress Index. */
async function fetchStress() {
    const since = new Date(Date.now() - 400 * 864e5).toISOString().slice(0, 10)
    const one = async (id) => {
        try {
            const pts = await fredSeries(id, since)
            const l = lastPt(pts)
            if (!l) return null
            const a = valueAgo(pts, 28)
            return { date: l[0], last: Math.round(l[1] * 10000) / 10000, chg1m: isNum(a) ? Math.round((l[1] - a) * 10000) / 10000 : null }
        } catch {
            return null
        }
    }
    const [credit, stress] = await Promise.all([one("NFCICREDIT"), one("STLFSI4")])
    return { credit, stress }
}

const ENERGY = [
    ["brent", "Brent Crude", "DCOILBRENTEU"],
    ["wti", "WTI Crude", "DCOILWTICO"],
    ["natgas", "Natural Gas (Henry Hub)", "DHHNGSP"],
]

/* ------------------------------------------------------------------ */
/* Time helpers                                                        */
/* ------------------------------------------------------------------ */

function nyNow(d = new Date()) {
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        weekday: "short",
        hour12: false,
    }).formatToParts(d)
    const g = (t) => parts.find((p) => p.type === t)?.value
    return {
        date: `${g("year")}-${g("month")}-${g("day")}`,
        hour: Number(g("hour")) % 24,
        weekday: g("weekday"), // "Mon" … "Sun"
    }
}

/** Market day the snapshot should cover: the last weekday whose 10 PM New York has passed. */
function targetDay(d = new Date()) {
    for (let k = 0; k < 8; k++) {
        const ny = nyNow(new Date(d.getTime() - k * 864e5))
        if (ny.weekday === "Sat" || ny.weekday === "Sun") continue
        if (k === 0 && ny.hour < RUN_HOUR_NY) continue
        return ny.date
    }
    return nyNow(d).date
}

/* ------------------------------------------------------------------ */
/* Indicators                                                          */
/* ------------------------------------------------------------------ */

const isNum = (v) => typeof v === "number" && isFinite(v)
const r4 = (v) => (isNum(v) ? Number(v.toPrecision(6)) : null)
const r2 = (v) => (isNum(v) ? Math.round(v * 100) / 100 : null)

function sma(c, n) {
    if (c.length < n) return null
    let s = 0
    for (let i = c.length - n; i < c.length; i++) s += c[i]
    return s / n
}
function smaAt(c, n, end) {
    if (end + 1 < n) return null
    let s = 0
    for (let i = end - n + 1; i <= end; i++) s += c[i]
    return s / n
}
const ret = (c, n) =>
    c.length > n ? (c[c.length - 1] / c[c.length - 1 - n] - 1) * 100 : null

/** pts: [[date, close], …] ascending. Returns the indicator block. */
export function computeIndicators(pts) {
    const c = pts.map((p) => p[1])
    const n = c.length
    if (n < 2) return null
    const last = c[n - 1]
    const lastDate = pts[n - 1][0]
    const year = lastDate.slice(0, 4)
    let ytdBase = null
    for (let i = n - 1; i >= 0; i--)
        if (pts[i][0].slice(0, 4) < year) {
            ytdBase = c[i]
            break
        }
    const win = c.slice(-252)
    const high52 = Math.max(...win)
    const low52 = Math.min(...win)
    // annualised volatility of daily log returns, last 63 sessions
    let vol = null
    if (n > 64) {
        const lr = []
        for (let i = n - 63; i < n; i++) lr.push(Math.log(c[i] / c[i - 1]))
        const m = lr.reduce((a, b) => a + b, 0) / lr.length
        const v = lr.reduce((a, b) => a + (b - m) ** 2, 0) / (lr.length - 1)
        vol = Math.sqrt(v) * Math.sqrt(252) * 100
    }
    const s50 = sma(c, 50)
    const s200 = sma(c, 200)
    // golden / death cross in the last 10 sessions
    let cross = null
    if (n >= 211) {
        for (let k = n - 10; k < n; k++) {
            const a0 = smaAt(c, 50, k - 1) - smaAt(c, 200, k - 1)
            const a1 = smaAt(c, 50, k) - smaAt(c, 200, k)
            if (a0 <= 0 && a1 > 0) cross = "golden"
            if (a0 >= 0 && a1 < 0) cross = "death"
        }
    }
    return {
        last,
        date: lastDate,
        d1: ret(c, 1),
        w1: ret(c, 5),
        m1: ret(c, 21),
        m3: ret(c, 63),
        m6: ret(c, 126),
        y1: ret(c, 252),
        ytd: ytdBase ? (last / ytdBase - 1) * 100 : null,
        sma50: s50,
        sma200: s200,
        high52,
        low52,
        offHigh: (last / high52 - 1) * 100,
        vol,
        cross,
    }
}

/** Same indicator block for MONTHLY points (OECD indices): 3- and 10-month averages stand in
    for the 50- and 200-day ones, the 1-year range uses 12 months, volatility 12 monthly returns. */
export function computeMonthly(pts) {
    const c = pts.map((p) => p[1])
    const n = c.length
    if (n < 2) return null
    const last = c[n - 1]
    const lastDate = pts[n - 1][0]
    const year = lastDate.slice(0, 4)
    let ytdBase = null
    for (let i = n - 1; i >= 0; i--)
        if (pts[i][0].slice(0, 4) < year) {
            ytdBase = c[i]
            break
        }
    const win = c.slice(-12)
    const high52 = Math.max(...win)
    const low52 = Math.min(...win)
    let vol = null
    if (n > 13) {
        const lr = []
        for (let i = n - 12; i < n; i++) lr.push(Math.log(c[i] / c[i - 1]))
        const m = lr.reduce((a, b) => a + b, 0) / lr.length
        const v = lr.reduce((a, b) => a + (b - m) ** 2, 0) / (lr.length - 1)
        vol = Math.sqrt(v) * Math.sqrt(12) * 100
    }
    const s3 = sma(c, 3)
    const s10 = sma(c, 10)
    // crossover of the 3- and 10-month averages in the latest month
    let cross = null
    if (n >= 11) {
        const a0 = smaAt(c, 3, n - 2) - smaAt(c, 10, n - 2)
        const a1 = s3 - s10
        if (a0 <= 0 && a1 > 0) cross = "golden"
        if (a0 >= 0 && a1 < 0) cross = "death"
    }
    return {
        last,
        date: lastDate,
        d1: null,
        w1: null,
        m1: ret(c, 1),
        m3: ret(c, 3),
        m6: ret(c, 6),
        y1: ret(c, 12),
        ytd: ytdBase ? (last / ytdBase - 1) * 100 : null,
        sma50: s3,
        sma200: s10,
        high52,
        low52,
        offHigh: (last / high52 - 1) * 100,
        vol,
        cross,
        freq: "monthly",
    }
}

/** Percentile rank of v inside arr (0..1). */
const pctRank = (arr, v) => {
    const xs = arr.filter(isNum)
    if (!xs.length || !isNum(v)) return 0.5
    return xs.filter((x) => x < v).length / Math.max(1, xs.length - 1)
}

/** Adds score, trend label and signals to every asset (needs the full list for ranks). */
export function scoreAll(assets) {
    const m1s = assets.map((a) => a.m1)
    const m3s = assets.map((a) => a.m3)
    for (const a of assets) {
        let s = 0
        let parts = 0
        if (isNum(a.sma50)) (s += a.last > a.sma50 ? 20 : 0), parts++
        if (isNum(a.sma200)) (s += a.last > a.sma200 ? 20 : 0), parts++
        if (isNum(a.sma50) && isNum(a.sma200))
            (s += a.sma50 > a.sma200 ? 20 : 0), parts++
        // rescale the moving-average part if some averages are missing
        s = parts ? (s / (parts * 20)) * 60 : 30
        s += pctRank(m3s, a.m3) * 25 + pctRank(m1s, a.m1) * 15
        a.score = Math.round(s)
        a.trend =
            a.score >= 75
                ? "Strong uptrend"
                : a.score >= 55
                  ? "Uptrend"
                  : a.score > 45
                    ? "Neutral"
                    : a.score > 25
                      ? "Downtrend"
                      : "Strong downtrend"
        const sig = []
        if (a.cross === "golden") sig.push("Golden cross")
        if (a.cross === "death") sig.push("Death cross")
        if (isNum(a.offHigh) && a.offHigh >= -1) sig.push("Near 52-week high")
        if (isNum(a.low52) && a.last <= a.low52 * 1.01)
            sig.push("Near 52-week low")
        if (isNum(a.sma200))
            sig.push(a.last > a.sma200 ? "Above 200-day" : "Below 200-day")
        if (isNum(a.m1) && isNum(a.m3) && a.m1 > 0 && a.m3 > 0 && a.m1 > a.m3 / 3)
            sig.push("Momentum accelerating")
        a.signals = sig
    }
    return assets
}

/** Keeps the last 260 daily points and one point a week before that. */
function compress(pts) {
    const recent = pts.slice(-260)
    const older = pts.slice(0, -260).filter((_, i, arr) => (arr.length - 1 - i) % 5 === 0)
    return [...older, ...recent].map(([d, v]) => [d, r4(v)])
}

/* ------------------------------------------------------------------ */
/* Sources                                                             */
/* ------------------------------------------------------------------ */

async function fetchTwelve(env, items) {
    const url =
        "https://api.twelvedata.com/time_series?symbol=" +
        encodeURIComponent(items.map((a) => a.td).join(",")) +
        "&interval=1day&outputsize=1300&order=ASC&apikey=" +
        env.TWELVE_KEY
    const r = await fetch(url)
    const j = await r.json()
    const out = {}
    for (const a of items) {
        const block = items.length === 1 ? j : j && j[a.td]
        if (block && Array.isArray(block.values)) {
            const pts = block.values
                .map((v) => [String(v.datetime).slice(0, 10), parseFloat(v.close)])
                .filter((p) => isNum(p[1]))
                .sort((x, y) => (x[0] < y[0] ? -1 : 1))
            if (pts.length > 1) out[a.id] = pts
        }
    }
    return { out, message: j && j.status === "error" ? j.message : "" }
}

/** Currencies from the ECB reference rates (EUR-based, converted to the usual quotes). */
async function fetchEcbFx(items) {
    const n = 1300
    const [usd, gbp, jpy, chf, cny] = await Promise.all(
        ["USD", "GBP", "JPY", "CHF", "CNY"].map((c) =>
            ecbSeries("EXR", `D.${c}.EUR.SP00.A`, n).catch(() => [])
        )
    )
    const map = (pts) => new Map(pts.map((q) => [q[0], q[1]]))
    const U = map(usd), G = map(gbp), J = map(jpy), C = map(chf), Y = map(cny)
    const build = (fn) =>
        usd
            .map(([d]) => [d, fn(d)])
            .filter((q) => isNum(q[1]))
    const series = {
        EURUSD: build((d) => U.get(d)),
        GBPUSD: build((d) => (G.get(d) ? U.get(d) / G.get(d) : NaN)),
        USDJPY: build((d) => (U.get(d) ? J.get(d) / U.get(d) : NaN)),
        USDCHF: build((d) => (U.get(d) ? C.get(d) / U.get(d) : NaN)),
        USDCNY: build((d) => (U.get(d) ? Y.get(d) / U.get(d) : NaN)),
    }
    const out = {}
    for (const a of items) if (series[a.id] && series[a.id].length > 1) out[a.id] = series[a.id]
    return { out, message: Object.keys(out).length ? "" : "ECB: no exchange-rate data" }
}

/** OECD share price indices, monthly, from FRED (about 7 years). */
async function fetchFredMonthly(items) {
    const since = new Date(Date.now() - 7 * 365 * 864e5).toISOString().slice(0, 10)
    const out = {}
    const msgs = []
    await Promise.all(
        items.map(async (a) => {
            try {
                const pts = await fredSeries(a.td, since)
                const last = pts[pts.length - 1]
                const tail = pts.slice(-4).map((p) => p[1])
                if (pts.length <= 12) msgs.push(`${a.name}: only ${pts.length} points`)
                // no update for ~9 months: the series has stopped
                else if (Date.now() - Date.parse(last[0]) > 270 * 864e5) msgs.push(`${a.name}: no data since ${last[0]}`)
                // same value 4 months in a row: frozen placeholder, not real prices
                else if (tail.every((v) => v === tail[0])) msgs.push(`${a.name}: frozen series (same value since ${pts[pts.length - 4][0]})`)
                else out[a.id] = pts
            } catch (e) {
                msgs.push(String((e && e.message) || e))
            }
        })
    )
    return { out, message: msgs.join(" · ") }
}

/** USD/RUB: Bank of Russia official rate (roubles per dollar), about 5 years, daily. */
async function fetchCbr(items) {
    const out = {}
    if (!items.some((a) => a.id === "USDRUB")) return { out, message: "" }
    const ddmmyyyy = (d) =>
        `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}/${d.getUTCFullYear()}`
    const from = new Date(Date.now() - 5 * 365 * 864e5)
    const url = `https://www.cbr.ru/scripts/XML_dynamic.asp?date_req1=${ddmmyyyy(from)}&date_req2=${ddmmyyyy(new Date())}&VAL_NM_RQ=R01235`
    try {
        const r = await fetch(url, { headers: { ...UA, Accept: "application/xml,text/xml,*/*" } })
        if (!r.ok) return { out, message: `Bank of Russia: HTTP ${r.status}` }
        const xml = await r.text()
        const pts = []
        for (const m of xml.matchAll(/<Record Date="(\d{2})\.(\d{2})\.(\d{4})"[\s\S]*?<Nominal>(\d+)<\/Nominal>\s*<Value>([\d,.]+)<\/Value>/g)) {
            const v = parseFloat(m[5].replace(",", ".")) / (parseFloat(m[4]) || 1)
            if (isNum(v)) pts.push([`${m[3]}-${m[2]}-${m[1]}`, v])
        }
        pts.sort((a, b) => (a[0] < b[0] ? -1 : 1))
        if (pts.length > 1) out.USDRUB = pts
        return { out, message: pts.length > 1 ? "" : "Bank of Russia: no data" }
    } catch (e) {
        return { out, message: "Bank of Russia: " + ((e && e.message) || e) }
    }
}

/** Crypto daily closes from CoinGecko (Demo plan: last 365 days). */
async function fetchCoinGecko(env, items) {
    const out = {}
    let message = ""
    for (const a of items) {
        const id = COINGECKO_ID[a.id]
        if (!id) continue
        try {
            const r = await fetch(
                `https://api.coingecko.com/api/v3/coins/${id}/market_chart?vs_currency=usd&days=365&interval=daily`,
                { headers: env.COINGECKO_KEY ? { "x-cg-demo-api-key": env.COINGECKO_KEY } : {} }
            )
            if (!r.ok) {
                message = `CoinGecko ${id}: HTTP ${r.status}`
                continue
            }
            const j = await r.json()
            const byDay = new Map()
            for (const [ts, v] of j.prices || []) if (isNum(v)) byDay.set(new Date(ts).toISOString().slice(0, 10), v)
            const pts = [...byDay.entries()].sort((x, y) => (x[0] < y[0] ? -1 : 1))
            if (pts.length > 1) out[a.id] = pts
        } catch (e) {
            message = "CoinGecko: " + ((e && e.message) || e)
        }
    }
    return { out, message }
}

/** A Worker cannot fetch another Worker of the same account on workers.dev (Cloudflare error 1042).
    With a Service binding named METALS the call goes Worker-to-Worker directly. */
function metalsFetch(env, url) {
    if (env.METALS && typeof env.METALS.fetch === "function") return env.METALS.fetch(new Request(url))
    return fetch(url)
}

const toDay = (d) => {
    if (typeof d === "number") return new Date(d < 1e11 ? d * 1000 : d).toISOString().slice(0, 10)
    return String(d).slice(0, 10)
}

let metalsError = ""
async function fetchMetal(env, id) {
    if (!env.METALS_URL) return null
    for (const range of ["max", "2y", "1y"]) {
        try {
            const u = new URL(env.METALS_URL)
            u.searchParams.set("history", id)
            u.searchParams.set("range", range)
            const r = await metalsFetch(env, u.toString())
            if (!r.ok) {
                metalsError = `HTTP ${r.status}` + (r.status === 404 || r.status >= 500 ? "" : "")
                continue
            }
            const j = await r.json()
            const pts = (j && j.points ? j.points : [])
                .map((p) =>
                    Array.isArray(p)
                        ? [p[0], Number(p[1])]
                        : p && typeof p === "object"
                          ? [p.t ?? p.date ?? p.d, Number(p.v ?? p.value ?? p.price)]
                          : [null, NaN]
                )
                .filter((p) => p[0] != null && isNum(p[1]))
                .map((p) => [toDay(p[0]), p[1]])
                .sort((a, b) => (a[0] < b[0] ? -1 : 1))
            if (pts.length > 30) return pts
            metalsError = `only ${pts.length} points for ${id} (${range})`
        } catch (e) {
            metalsError = String((e && e.message) || e)
        }
    }
    return null
}

// Small shape-tolerant reader for the CEII crude.json answer
function energySeries(json, keys) {
    const lc = (o) =>
        Object.fromEntries(Object.entries(o || {}).map(([k, v]) => [k.toLowerCase(), v]))
    const found = []
    const walk = (node, depth) => {
        if (!node || typeof node !== "object" || depth > 4) return
        if (Array.isArray(node)) return node.forEach((x) => walk(x, depth + 1))
        const o = lc(node)
        const label = String(o.name || o.label || o.title || o.symbol || o.id || "").toLowerCase()
        for (const k of ["series", "history", "points", "values", "data", "prices", "days"]) {
            if (Array.isArray(o[k]) && o[k].length > 30 && label) {
                const pts = o[k]
                    .map((x) =>
                        Array.isArray(x)
                            ? [x[0], Number(x[1])]
                            : x && typeof x === "object"
                              ? (() => {
                                    const q = lc(x)
                                    return [
                                        q.date || q.t || q.time || q.period || q.day,
                                        Number(q.value ?? q.price ?? q.close ?? q.v ?? q.y),
                                    ]
                                })()
                              : [null, NaN]
                    )
                    .filter((p) => p[0] && isNum(p[1]) && !isNaN(Date.parse(p[0])))
                    .map((p) => [new Date(p[0]).toISOString().slice(0, 10), p[1]])
                    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
                if (pts.length > 30) found.push({ label, pts })
            }
        }
        Object.values(node).forEach((v) => walk(v, depth + 1))
    }
    walk(json, 0)
    const hit = found.find((f) => keys.some((k) => f.label.includes(k)))
    return hit ? hit.pts : null
}

/* ------------------------------------------------------------------ */
/* Daily run                                                           */
/* ------------------------------------------------------------------ */

/** Drop the edge-cached copy of /signals so readers get the new snapshot at once. */
async function purgeSignalsCache(origin) {
    try {
        if (typeof caches !== "undefined" && origin) await caches.default.delete(new Request(origin + "/signals", { method: "GET" }))
    } catch {}
}

async function assemble(env, date) {
    let metalsProblem = ""
    const assets = []
    const add = (meta, raw, stale, monthly) => {
        // keep only closes up to the day this snapshot covers (a catch-up run the next day
        // must not add that day's unfinished prices)
        const pts = raw && raw.filter((p) => p[0] <= date)
        const ind = pts && (monthly ? computeMonthly(pts) : computeIndicators(pts))
        if (!ind) return
        assets.push({ ...meta, ...ind, hist: compress(pts), stale: !!stale })
    }
    for (const a of activeUniverse(env)) {
        const raw = await env.EB_SIGNALS.get("a:" + a.id)
        if (raw) {
            const o = JSON.parse(raw)
            add({ id: a.id, name: a.name, cls: a.cls }, o.pts, o.date !== date, a.src === "fredm")
        }
    }
    for (const [id, name] of METALS) {
        const pts = await fetchMetal(env, id)
        add({ id, name, cls: "Metals" }, pts, false)
        if (!pts) metalsProblem = metalsError || "no data"
    }
    // energy: ~5 years of daily spot prices (3 requests)
    let energyProblem = ""
    const since = new Date(Date.now() - 1900 * 864e5).toISOString().slice(0, 10)
    const energy = await Promise.all(
        ENERGY.map(([, , series]) =>
            fredSeries(series, since).catch((e) => {
                energyProblem = String((e && e.message) || e)
                return null
            })
        )
    )
    ENERGY.forEach(([id, name], i) => add({ id, name, cls: "Energy" }, energy[i], false))

    scoreAll(assets)
    const isN = (v) => typeof v === "number" && isFinite(v)
    const with200 = assets.filter((a) => isN(a.sma200))
    const with50 = assets.filter((a) => isN(a.sma50))
    // date of the last U.S. market close in the data (SPY, else the most common last date)
    const spy = assets.find((a) => a.id === "SPY")
    const dates = assets.filter((a) => !["Crypto"].includes(a.cls)).map((a) => a.date).filter(Boolean).sort()
    const marketDate = (spy && spy.date) || dates[dates.length - 1] || date
    const payload = {
        v: 2,
        metalsProblem: metalsProblem || undefined,
        energyProblem: energyProblem || undefined,
        asOf: date,
        marketDate,
        generated: new Date().toISOString(),
        breadth: {
            above200: with200.length
                ? (with200.filter((a) => a.last > a.sma200).length / with200.length) * 100
                : null,
            above50: with50.length
                ? (with50.filter((a) => a.last > a.sma50).length / with50.length) * 100
                : null,
        },
        assets: assets.map((a) => {
            const o = { ...a }
            for (const k of ["d1", "w1", "m1", "m3", "m6", "y1", "ytd", "offHigh", "vol"]) o[k] = r2(o[k])
            for (const k of ["last", "sma50", "sma200", "high52", "low52"]) o[k] = r4(o[k])
            return o
        }),
    }
    try {
        payload.yields = await fetchYields(env)
    } catch (e) {
        payload.yields = { rows: [], curve: null, problem: String((e && e.message) || e) }
    }
    try {
        payload.stress = await fetchStress()
    } catch {}
    if (env.FINNHUB_KEY) {
        try {
            payload.stocks = await assembleStocks(env)
        } catch (e) {
            payload.stocksError = String((e && e.message) || e)
        }
    }
    await env.EB_SIGNALS.put("signals:latest", JSON.stringify(payload))
    // small key read by every cron tick to know whether there is anything to do
    await env.EB_SIGNALS.put("signals:asOf", date)
    return payload
}

/** One step of the daily job. Safe to call many times. */
export async function runSignals(rawEnv, force = false, reset = false) {
    const env = withDefaults(rawEnv)
    const ny = nyNow()
    // the market day to cover: today after 10 PM New York, otherwise the previous weekday
    // (weekends and Monday before 10 PM point to Friday)
    const day = targetDay()
    if (!force) {
        const covered = await env.EB_SIGNALS.get("signals:asOf")
        if (covered && covered >= day) return { skipped: "up to date", day, ny }
    }
    const key = "run:" + day
    const state = JSON.parse((await env.EB_SIGNALS.get(key)) || "{}")
    state.done = state.done || []
    state.tries = state.tries || {}

    // the stock data format changed (news added): download today's stocks again once
    if (state.v !== STATE_VERSION) {
        state.sdone = []
        state.assembled = false
        state.v = STATE_VERSION
    }
    if (force && reset) {
        state.done = []
        state.sdone = []
        state.tries = {}
        state.assembled = false
    }
    state.sdone = state.sdone || []
    const stockList = env.FINNHUB_KEY ? STOCKS : []
    const todo = activeUniverse(env).filter((a) => !state.done.includes(a.id)).slice(0, BATCH)
    const stodo = stockList.filter((s) => !state.sdone.includes(s.ticker)).slice(0, STOCK_BATCH)
    let message = ""
    if (todo.length) {
        let out = {}
        let m = ""
        const msgs = []
        const groups = [
            ["twelve", (list) => fetchTwelve(env, list)],
            ["ecb", (list) => fetchEcbFx(list)],
            ["coingecko", (list) => fetchCoinGecko(env, list)],
            ["fredm", (list) => fetchFredMonthly(list)],
            ["cbr", (list) => fetchCbr(list)],
        ]
        for (const [src, fn] of groups) {
            const list = todo.filter((a) => a.src === src)
            if (!list.length) continue
            try {
                const res = await fn(list)
                Object.assign(out, res.out)
                if (res.message) msgs.push(res.message)
            } catch (e) {
                msgs.push(src + " request failed: " + ((e && e.message) || e))
            }
        }
        m = msgs.join(" · ")
        message = m
        for (const a of todo) {
            if (out[a.id]) {
                await env.EB_SIGNALS.put("a:" + a.id, JSON.stringify({ date: day, pts: out[a.id].filter((p) => p[0] <= day) }))
                state.done.push(a.id)
            } else {
                state.tries[a.id] = (state.tries[a.id] || 0) + 1
                // after 2 failed tries keep yesterday's data (marked "stale")
                if (state.tries[a.id] >= 2) state.done.push(a.id)
            }
        }
    }
    let stockMsg = ""
    if (stodo.length) {
        // find the working key first (max 2 requests), so the batch stays under 50 requests
        if (!goodFinnhubKey) await finnhub(env, "/stock/profile2?symbol=AAPL").catch(() => {})
        const got = await Promise.all(stodo.map((s) => fetchStock(env, s.ticker)))
        for (const [i, s] of stodo.entries()) {
            const g = got[i]
            if (g.ok) await env.EB_SIGNALS.put("s:" + s.ticker, JSON.stringify({ date: day, ...g.data }))
            else stockMsg = stockMsg || `${s.ticker}: ${g.error}`
            state.sdone.push(s.ticker) // one try per night; yesterday's data stays if it failed
        }
    }
    // new data arrived in this run → the snapshot must be rebuilt (even if it was built earlier today)
    if (todo.length || stodo.length) state.assembled = false
    const left = activeUniverse(env).filter((a) => !state.done.includes(a.id)).length
    const stocksLeft = stockList.filter((s) => !state.sdone.includes(s.ticker)).length
    // assemble in a run of its own once everything is downloaded (keeps each run under 50 requests)
    if (!left && !stocksLeft && !stodo.length && !state.assembled) {
        await assemble(env, day)
        state.assembled = true
        await purgeSignalsCache(await env.EB_SIGNALS.get("origin"))
    }
    await env.EB_SIGNALS.put(key, JSON.stringify(state), { expirationTtl: 5 * 86400 })
    return {
        date: day,
        fetched: todo.map((a) => a.id),
        stocks: stodo.map((s) => s.ticker),
        left,
        stocksLeft,
        assembled: !!state.assembled,
        message: [message, stockMsg].filter(Boolean).join(" · "),
        ...(env.FINNHUB_KEY ? {} : { note: "No FINNHUB_KEY: stock analysis skipped" }),
    }
}

let goodFinnhubKey = ""
async function finnhub(env, path) {
    const keys = String(env.FINNHUB_KEY || "")
        .split(/[,\s]+/)
        .filter(Boolean)
    const order = goodFinnhubKey ? [goodFinnhubKey, ...keys.filter((k) => k !== goodFinnhubKey)] : keys
    let last = 0
    for (const k of order) {
        const r = await fetch(`https://finnhub.io/api/v1${path}${path.includes("?") ? "&" : "?"}token=${k}`)
        if (r.status === 401 || r.status === 403) {
            last = r.status
            continue // wrong key: try the next one
        }
        if (!r.ok) throw new Error("HTTP " + r.status)
        goodFinnhubKey = k
        return r.json()
    }
    throw new Error("Finnhub refused the key (HTTP " + last + ")")
}

/** metric + profile + latest analyst recommendation for one ticker (3 requests). */
async function fetchStock(env, ticker) {
    try {
        const t = encodeURIComponent(ticker)
        const to = new Date().toISOString().slice(0, 10)
        const from = new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 10)
        const [met, prof, rec, news] = await Promise.all([
            finnhub(env, `/stock/metric?symbol=${t}&metric=all`),
            finnhub(env, `/stock/profile2?symbol=${t}`).catch(() => ({})),
            finnhub(env, `/stock/recommendation?symbol=${t}`).catch(() => []),
            finnhub(env, `/company-news?symbol=${t}&from=${from}&to=${to}`).catch(() => []),
        ])
        const raw = (met && met.metric) || {}
        if (!Object.keys(raw).length) return { ok: false, error: "no metrics (not covered by the free plan?)" }
        const metric = {}
        for (const k of SK_KEYS) if (finite(raw[k])) metric[k] = raw[k]
        return {
            ok: true,
            data: {
                metric,
                profile: {
                    name: prof.name || "",
                    logo: prof.logo || "",
                    industry: prof.finnhubIndustry || "",
                    country: prof.country || "",
                    web: prof.weburl || "",
                    currency: prof.currency || "",
                },
                rec: Array.isArray(rec) && rec.length ? rec[0] : null,
                news: newsStats(news),
            },
        }
    } catch (e) {
        return { ok: false, error: String((e && e.message) || e) }
    }
}

async function assembleStocks(env) {
    const list = []
    for (const s of STOCKS) {
        const raw = await env.EB_SIGNALS.get("s:" + s.ticker)
        if (!raw) continue
        const o = JSON.parse(raw)
        list.push({
            ticker: s.ticker,
            name: s.name,
            country: s.country,
            logo: o.profile && o.profile.logo,
            industry: o.profile && o.profile.industry,
            web: o.profile && o.profile.web,
            date: o.date,
            m: extractMetrics(o.metric),
            rec: o.rec,
            news: o.news || null,
        })
    }
    if (list.length < 5) return null
    scoreStocks(list)
    return { universe: list.length, medians: stockMedians(list), list }
}

/* ------------------------------------------------------------------ */
/* Daily check: alert only when something is wrong                     */
/* ------------------------------------------------------------------ */

/** Everything that is wrong with a snapshot, in plain words (empty = all good). */
function checkProblems(env, j) {
    if (!j) return ["No snapshot stored yet"]
    const issues = []
    const day = targetDay()
    if (j.asOf < day) issues.push(`Data late: the snapshot covers ${j.asOf}, it should cover ${day}`)
    const ignore = String(env.ALERT_IGNORE ?? "Russia")
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean)
    const names = [...activeUniverse(env).map((a) => a.name), ...METALS.map((m) => m[1]), ...ENERGY.map((e) => e[1])]
    const missing = names.filter((n) => !ignore.includes(n) && !(j.assets || []).some((a) => a.name === n))
    if (missing.length) issues.push(`Missing: ${missing.join(", ")}`)
    const stale = (j.assets || []).filter((a) => a.stale).map((a) => a.name)
    if (stale.length) issues.push(`Old data kept (source failed): ${stale.join(", ")}`)
    if (j.metalsProblem) issues.push(`Metals: ${j.metalsProblem}`)
    if (j.energyProblem) issues.push(`Energy: ${j.energyProblem}`)
    if (j.yields && j.yields.problem) issues.push(`Yields: ${j.yields.problem}`)
    const staleY = ((j.yields && j.yields.rows) || []).filter((r) => r.stale).map((r) => r.country)
    if (staleY.length) issues.push(`Yields kept from the previous update: ${staleY.join(", ")}`)
    if (!j.stress || !j.stress.credit || !j.stress.stress) issues.push("Market Mood: Federal Reserve indices missing")
    if (env.FINNHUB_KEY && !j.stocks) issues.push(`Stock analysis missing${j.stocksError ? ": " + j.stocksError : ""}`)
    return issues
}

/** Sends the alert to ntfy.sh, Discord or Slack (format chosen from the URL). */
async function sendAlert(env, title, lines) {
    const url = String(env.ALERT_WEBHOOK || "").trim()
    if (!url) return { sent: false, reason: "No ALERT_WEBHOOK set" }
    const text = title + "\n" + lines.map((l) => "• " + l).join("\n")
    let headers = { "Content-Type": "application/json" }
    let body
    if (/discord(app)?\.com\/api\/webhooks/.test(url)) body = JSON.stringify({ content: text.slice(0, 1900) })
    else if (/hooks\.slack\.com/.test(url)) body = JSON.stringify({ text })
    else {
        // ntfy.sh (or any service that takes plain text)
        headers = { "Content-Type": "text/plain; charset=utf-8", Title: "EB Signals", Tags: "warning" }
        body = text
    }
    try {
        const r = await fetch(url, { method: "POST", headers, body })
        return { sent: r.ok, status: r.status }
    } catch (e) {
        return { sent: false, reason: String((e && e.message) || e) }
    }
}

/** Once a day at ALERT_HOUR (local time): check the snapshot, alert only if something is wrong. */
async function dailyCheck(env, force = false, test = false) {
    const tz = env.ALERT_TZ || "Europe/Paris"
    const hour = Number(env.ALERT_HOUR ?? 8)
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hour12: false }).formatToParts(new Date())
    const g = (t) => (parts.find((p) => p.type === t) || {}).value
    const localDate = `${g("year")}-${g("month")}-${g("day")}`
    if (!force && Number(g("hour")) % 24 !== hour) return { skipped: true }
    const key = "alert:" + localDate
    if (!force && (await env.EB_SIGNALS.get(key))) return { skipped: "already checked today" }
    let j = null
    try {
        j = JSON.parse((await env.EB_SIGNALS.get("signals:latest")) || "null")
    } catch {}
    const issues = checkProblems(env, j)
    if (!force) await env.EB_SIGNALS.put(key, "1", { expirationTtl: 3 * 86400 })
    if (!issues.length)
        return {
            ok: true,
            issues,
            alert: test ? await sendAlert(env, `EB Signals: all good (${localDate}), snapshot ${j && j.asOf}`, ["Test message"]) : null,
        }
    const alert = await sendAlert(env, `EB Signals: ${issues.length} problem${issues.length > 1 ? "s" : ""} (${localDate})`, issues)
    return { ok: false, issues, alert }
}

/* ------------------------------------------------------------------ */
/* HTTP                                                                */
/* ------------------------------------------------------------------ */

function hostOf(origin) {
    try {
        return new URL(origin).hostname
    } catch {
        return "" // "null" or empty Origin (Framer canvas, direct visit)
    }
}

function cors(request, env) {
    const allowed = String((env && env.ALLOWED_ORIGINS) || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    const origin = request.headers.get("Origin") || ""
    const ok =
        !allowed.length ||
        allowed.includes(origin) ||
        /\.framer\.(app|website|com|photos)$/.test(hostOf(origin))
    return {
        "Access-Control-Allow-Origin": !allowed.length ? "*" : ok ? origin : allowed[0],
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        Vary: "Origin",
    }
}

/** What is missing in the Worker settings (shown by /signals/health and in errors). */
function checkSetup(env) {
    const missing = []
    if (!env || !env.EB_SIGNALS || typeof env.EB_SIGNALS.get !== "function")
        missing.push("KV binding EB_SIGNALS (Settings → Bindings → KV namespace, variable name EB_SIGNALS)")
    if (env && env.TWELVE_LICENSED && !env.TWELVE_KEY) missing.push("Secret TWELVE_KEY (Settings → Variables and Secrets)")
    return missing
}

export async function handleSignals(request, rawEnv, ctx) {
    const env = withDefaults(rawEnv)
    let h = { "Access-Control-Allow-Origin": "*" }
    try {
        h = cors(request, env)
        return await route(request, env, ctx, h)
    } catch (e) {
        // never a bare Cloudflare 1101: say what went wrong
        return Response.json(
            { error: String((e && e.message) || e), missing: checkSetup(env) },
            { status: 500, headers: h }
        )
    }
}

async function route(request, env, ctx, h) {
    const url = new URL(request.url)
    // remember our own address so the nightly job can clear the edge cache
    if (env.EB_SIGNALS && ctx && ctx.waitUntil)
        ctx.waitUntil(
            env.EB_SIGNALS.get("origin").then((o) => (o !== url.origin ? env.EB_SIGNALS.put("origin", url.origin) : null)).catch(() => {})
        )
    if (request.method === "OPTIONS") return new Response(null, { headers: h })

    const missing = checkSetup(env)

    // GET /signals/health → setup check, safe to open in a browser
    if (url.pathname === "/signals/health" || url.pathname === "/health") {
        let snapshot = null
        if (!missing.some((m) => m.startsWith("KV"))) {
            const raw = await env.EB_SIGNALS.get("signals:latest")
            if (raw) {
                const j = JSON.parse(raw)
                snapshot = {
                    problems: checkProblems(env, j),
                    asOf: j.asOf,
                    marketDate: j.marketDate,
                    generated: j.generated,
                    assets: (j.assets || []).length,
                    stocks: j.stocks ? j.stocks.list.length : 0,
                    metalsProblem: j.metalsProblem || null,
                    energyProblem: j.energyProblem || null,
                    yields: j.yields ? j.yields.rows.length : 0,
                    yieldsProblem: (j.yields && j.yields.problem) || null,
                    twelveLicensed: !!env.TWELVE_LICENSED,
                    missingAssets: [...activeUniverse(env).map((a) => a.name), ...METALS.map((m) => m[1]), ...ENERGY.map((e) => e[1])].filter(
                        (n) => !(j.assets || []).some((a) => a.name === n)
                    ),
                }
            }
        }
        return Response.json(
            { ok: !missing.length, missing, snapshot, newYork: nyNow(), targetDay: targetDay(), alertWebhook: !!env.ALERT_WEBHOOK, runToken: !!env.RUN_TOKEN, metalsUrl: env.METALS_URL || null, metalsBinding: !!(env.METALS && env.METALS.fetch), finnhubKey: !!env.FINNHUB_KEY, finnhubKeyInUse: goodFinnhubKey ? goodFinnhubKey.slice(0, 4) + "…" + goodFinnhubKey.slice(-3) : null },
            { headers: h }
        )
    }

    if (missing.length)
        return Response.json({ error: "Worker setup incomplete", missing }, { status: 500, headers: h })

    // GET /signals/stock-debug?t=NVDA&token=… → raw Finnhub answer, to check field names
    if (url.pathname === "/signals/stock-debug") {
        if (url.searchParams.get("token") !== env.RUN_TOKEN) return new Response("Forbidden", { status: 403, headers: h })
        if (!env.FINNHUB_KEY) return Response.json({ error: "No FINNHUB_KEY" }, { headers: h })
        const res = await fetchStock(env, url.searchParams.get("t") || "NVDA")
        return Response.json(res.ok ? { ...res, extracted: extractMetrics(res.data.metric) } : res, { headers: h })
    }

    // GET /signals/check?token=…(&test=1) → run the daily check now
    if (url.pathname === "/signals/check") {
        if (url.searchParams.get("token") !== env.RUN_TOKEN) return new Response("Forbidden", { status: 403, headers: h })
        return Response.json(await dailyCheck(env, true, url.searchParams.get("test") === "1"), { headers: h })
    }

    // GET /signals/yields-debug?token=… → fetch the yields now, without saving (to test the sources)
    if (url.pathname === "/signals/yields-debug") {
        if (url.searchParams.get("token") !== env.RUN_TOKEN) return new Response("Forbidden", { status: 403, headers: h })
        return Response.json(await fetchYields(env), { headers: h })
    }

    // GET /signals/refresh-yields?token=… → fetch the yields and add them to today's snapshot at once
    if (url.pathname === "/signals/refresh-yields") {
        if (url.searchParams.get("token") !== env.RUN_TOKEN) return new Response("Forbidden", { status: 403, headers: h })
        const raw = await env.EB_SIGNALS.get("signals:latest")
        if (!raw) return Response.json({ error: "No snapshot yet: run /signals/run first" }, { status: 404, headers: h })
        const j = JSON.parse(raw)
        j.yields = await fetchYields(env)
        await env.EB_SIGNALS.put("signals:latest", JSON.stringify(j))
        await purgeSignalsCache(url.origin)
        return Response.json({ ok: true, yields: j.yields.rows.length, problem: j.yields.problem || null }, { headers: h })
    }

    if (url.pathname === "/signals/run") {
        if (!env.RUN_TOKEN || url.searchParams.get("token") !== env.RUN_TOKEN)
            return Response.json(
                { error: env.RUN_TOKEN ? "Wrong token" : "Add the secret RUN_TOKEN first, then call /signals/run?token=YOUR_TOKEN" },
                { status: 403, headers: h }
            )
        const res = await runSignals(env, true, url.searchParams.get("reset") === "1")
        if (res && res.assembled) await purgeSignalsCache(url.origin)
        return Response.json(res, { headers: h })
    }

    // GET /signals (or / when deployed on its own) → latest snapshot, edge-cached 10 minutes
    const cache = typeof caches !== "undefined" ? caches.default : null
    const cacheKey = new Request(url.origin + "/signals", { method: "GET" })
    let res = cache ? await cache.match(cacheKey) : undefined
    if (!res) {
        const body = await env.EB_SIGNALS.get("signals:latest")
        if (!body)
            return Response.json(
                { error: "No snapshot yet. Open /signals/run?token=YOUR_TOKEN about 6 times, one minute apart, or wait for 10 PM New York." },
                { status: 404, headers: h }
            )
        res = new Response(body, {
            headers: { "Content-Type": "application/json", "Cache-Control": "public, max-age=600" },
        })
        if (cache && ctx && ctx.waitUntil) ctx.waitUntil(cache.put(cacheKey, res.clone()))
    }
    const out = new Response(res.body, res)
    Object.entries(h).forEach(([k, v]) => out.headers.set(k, v))
    return out
}

export default {
    fetch: (request, env, ctx) => handleSignals(request, env, ctx),
    scheduled: (event, rawEnv, ctx) => {
        const env = withDefaults(rawEnv)
        ctx.waitUntil(
            checkSetup(env).length
                ? Promise.resolve()
                : Promise.all([
                      runSignals(env).catch((e) => console.log("EB signals run failed:", e && e.message)),
                      dailyCheck(env).catch((e) => console.log("EB daily check failed:", e && e.message)),
                  ])
        )
    },
}