import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

/**
 * THE ANALYST — Daily Market Analysis & Intelligence · Economic Bearings
 * Same look as EB Islamic Investment: flat beige page, serif titles and numbers,
 * thin rules, ▲ green / ▼ red, blue links. Clean editorial layout, two charts only.
 *
 * DATA
 *  - Data URL: eb-analyst.json, published every day at 06:30 New York by the
 *    EB Analyst engine (GitHub). It reads our own pages' data (Financial Markets,
 *    Energy Terminal, Crypto & Currencies, Hard Assets, Estate Index, Corporate
 *    Monitor, Market Outlook, Islamic Investment) and world news volume (GDELT /
 *    Google News). The text is drafted with a free AI model from those facts and
 *    every figure is checked automatically before publication.
 *  - With "Data URL" empty the component shows SAMPLE data.
 *  - Links in the text are written [[key|words]]; "Page links" maps each key to a page.
 *
 * Not investment advice. No cookies, no third-party scripts, no API key.
 *
 * @framerIntrinsicWidth 1280
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type Mkt = {
    id: string
    ok?: boolean
    name: string
    class?: string
    page?: string
    kind?: string
    last?: number
    lastText?: string
    d1?: number | null
    d1Text?: string
    w1Text?: string
    m1Text?: string
    z?: number
    size?: string
    asOf?: string
    stale?: boolean
}
type Bar = {
    id: string
    name: string
    class: string
    z: number
    text: string
    page: string
    stale?: boolean
}
type Theme = {
    id: string
    label: string
    status: string
    spike: number | null
    direction?: string | null
    consistent: string[]
    against: string[]
    headlines: { title: string; url: string; source: string; date: string }[]
    newsSource?: string | null
}
type Data = {
    version?: number
    generated?: string
    sample?: boolean
    edition: { date: string; weekday: string; mode: string; basedOn: string }
    nextEdition: string
    writtenBy: string
    override?: boolean
    regime: { id: string; label: string; score: number; members: string[] }
    lead: { type: string; id: string; label: string; assets: string[] }
    text: {
        headline: string
        tone: string
        lead: string[]
        briefs: Record<string, string>
        watch: string[]
    }
    kpis: Mkt[]
    bars: Bar[]
    context: {
        title: string
        note: string
        series: {
            id: string
            name: string
            unit: string
            page: string
            points: [string, number][]
        }[]
    }
    themes: Theme[]
    markets?: Record<string, Mkt>
    pages: Record<string, string>
    sources: string
    news?: { theme: string; title: string; url: string; source: string; date: string }[]
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const isNum = (v: any): v is number => typeof v === "number" && isFinite(v)
const sgn = (v: number | null | undefined) =>
    !isNum(v) || v === 0 ? 0 : v > 0 ? 1 : -1
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))
const fam = (f: any, fallback: string) =>
    f && f.fontFamily
        ? '"' + String(f.fontFamily).replace(/"/g, "") + '",' + fallback
        : ""
const fmtDay = (iso: string | null | undefined, o: Intl.DateTimeFormatOptions) => {
    if (!iso) return ""
    try {
        return new Date(
            iso.length <= 10 ? iso + "T12:00:00Z" : iso
        ).toLocaleDateString("en-US", { timeZone: "UTC", ...o })
    } catch {
        return iso
    }
}
const fmtLeft = (ms: number) => {
    const m = Math.max(0, Math.round(ms / 60000))
    const h = Math.floor(m / 60)
    return h ? `${h} h ${String(m % 60).padStart(2, "0")}` : `${m} min`
}

const STORE = "ean:v1:"
const readStore = (k: string): any => {
    try {
        return JSON.parse(window.localStorage.getItem(STORE + k) || "null")
    } catch {
        return null
    }
}
const writeStore = (k: string, v: any) => {
    try {
        window.localStorage.setItem(STORE + k, JSON.stringify(v))
    } catch {}
}

function useWidth(ref: React.RefObject<HTMLElement | null>) {
    const [w, setW] = React.useState(1200)
    React.useLayoutEffect(() => {
        const el = ref.current
        if (!el) return
        setW(el.getBoundingClientRect().width || 1200)
        if (typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((e) => setW(e[0].contentRect.width))
        ro.observe(el)
        return () => ro.disconnect()
    }, [])
    return w
}

/** "[[energy|Brent crude]]" -> link to the Energy Terminal page. */
function Rich({
    text,
    href,
}: {
    text: string
    href: (key: string) => string
}) {
    const parts: React.ReactNode[] = []
    const re = /\[\[([a-z]+)\|([^\]]+)\]\]/g
    let last = 0
    let m: RegExpExecArray | null
    let i = 0
    while ((m = re.exec(text || ""))) {
        if (m.index > last) parts.push(text.slice(last, m.index))
        const url = href(m[1])
        parts.push(
            url ? (
                <a key={i++} className="ean-a" href={url} target="_blank" rel="noopener">
                    {m[2]}
                </a>
            ) : (
                <React.Fragment key={i++}>{m[2]}</React.Fragment>
            )
        )
        last = m.index + m[0].length
    }
    if (last < (text || "").length) parts.push(text.slice(last))
    return <>{parts}</>
}

function Pct({ m }: { m: Mkt }) {
    const s = sgn(m.d1)
    const t = (m.d1Text || "—").replace(/^[+−-]/, "")
    return (
        <span className={s > 0 ? "ean-up" : s < 0 ? "ean-dn" : "ean-mut"}>
            {s > 0 ? "▲ " : s < 0 ? "▼ " : ""}
            {t}
        </span>
    )
}

function Panel({
    title,
    note,
    children,
}: {
    title: string
    note?: string
    children: React.ReactNode
}) {
    return (
        <section className="ean-panel">
            <header className="ean-ph">
                <h3>{title}</h3>
                {note && <span className="ean-note">{note}</span>}
            </header>
            {children}
        </section>
    )
}

/* ------------------------------------------------------------------ */
/* Chart 1: today's moves, scaled to each market's usual daily swing    */
/* ------------------------------------------------------------------ */

function MoveBars({
    rows,
    href,
}: {
    rows: Bar[]
    href: (key: string) => string
}) {
    const M = 3
    return (
        <div className="ean-mb" role="list">
            {rows.map((r) => {
                const z = clamp(r.z || 0, -M, M)
                const w = (Math.abs(z) / M) * 50
                const up = z > 0
                const strong = Math.abs(r.z) >= 1
                return (
                    <div
                        key={r.id}
                        className="ean-mbr"
                        role="listitem"
                        title={`${r.name}: ${r.text} (${Math.abs(r.z).toFixed(1)}× its usual daily move)`}
                    >
                        <a className="ean-mbn" href={href(r.page) || undefined} target="_blank" rel="noopener">
                            {r.name.replace(/ \(.*\)$/, "")}
                        </a>
                        <span className="ean-mbt">
                            <em />
                            <i
                                style={{
                                    left: up ? "50%" : 50 - w + "%",
                                    width: w + "%",
                                    background: up ? "var(--up)" : "var(--dn)",
                                    opacity: strong ? 1 : 0.38,
                                }}
                            />
                        </span>
                        <span
                            className={
                                "ean-mbv " +
                                (strong ? (up ? "ean-up" : "ean-dn") : "")
                            }
                        >
                            {r.text}
                        </span>
                    </div>
                )
            })}
            <div className="ean-mbs">
                <span>Unusually weak</span>
                <span>usual range</span>
                <span>Unusually strong</span>
            </div>
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Chart 2: the lead story over one month                              */
/* ------------------------------------------------------------------ */

function ContextChart({
    series,
    colors,
    height,
}: {
    series: Data["context"]["series"]
    colors: string[]
    height: number
}) {
    const ref = React.useRef<HTMLDivElement>(null)
    const W = Math.max(260, useWidth(ref))
    const H = height
    const [hover, setHover] = React.useState<number | null>(null)
    const unit = series[0]?.unit || "%"
    const n = Math.max(0, ...series.map((s) => s.points.length))
    const all = series.flatMap((s) => s.points.map((p) => p[1]))
    if (n < 2 || !all.length)
        return (
            <div ref={ref} className="ean-empty" style={{ height: H }}>
                Chart appears with the next edition.
            </div>
        )
    const padL = 4
    const padR = 58
    const padT = 10
    const padB = 22
    let lo = Math.min(0, ...all)
    let hi = Math.max(0, ...all)
    const sp = hi - lo || 1
    lo -= sp * 0.08
    hi += sp * 0.08
    const steps = [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100]
    const step = steps.find((s) => (hi - lo) / s <= 5) || 200
    const ticks: number[] = []
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step)
        ticks.push(+v.toFixed(4))
    const x = (i: number) => padL + (i / (n - 1)) * (W - padL - padR)
    const y = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB)
    const lab = (v: number) =>
        (v > 0 ? "+" : v < 0 ? "−" : "") +
        Math.abs(v).toFixed(step < 1 ? 1 : 0) +
        (unit === "bp" ? " bp" : "%")
    const dates = (series.find((s) => s.points.length === n) || series[0]).points.map(
        (p) => p[0]
    )
    const ends = series
        .map((s, k) => ({
            k,
            v: s.points[s.points.length - 1]?.[1] ?? 0,
            y: y(s.points[s.points.length - 1]?.[1] ?? 0),
        }))
        .sort((a, b) => a.y - b.y)
    for (let i = 1; i < ends.length; i++)
        if (ends[i].y - ends[i - 1].y < 16) ends[i].y = ends[i - 1].y + 16
    return (
        <div ref={ref} className="ean-chart" style={{ position: "relative" }}>
            <svg
                width={W}
                height={H}
                role="img"
                aria-label={series
                    .map((s) => `${s.name} ${lab(s.points[s.points.length - 1]?.[1] ?? 0)}`)
                    .join(", ")}
            >
                {ticks.map((v) => (
                    <g key={v}>
                        <line
                            x1={padL}
                            x2={W - padR + 4}
                            y1={y(v)}
                            y2={y(v)}
                            className={v === 0 ? "ean-zero" : "ean-gl"}
                        />
                        <text x={W - padR + 8} y={y(v) + 3.5} className="ean-axis">
                            {lab(v)}
                        </text>
                    </g>
                ))}
                {[0, Math.floor((n - 1) / 2), n - 1].map((i, k) => (
                    <text
                        key={k}
                        x={x(i)}
                        y={H - 6}
                        className="ean-axis"
                        textAnchor={k === 0 ? "start" : k === 2 ? "end" : "middle"}
                    >
                        {fmtDay(dates[i], { month: "short", day: "numeric" })}
                    </text>
                ))}
                {series.map((s, k) => (
                    <path
                        key={s.id}
                        d={s.points
                            .map(
                                (p, i) =>
                                    (i ? "L" : "M") +
                                    x(i + (n - s.points.length)).toFixed(1) +
                                    "," +
                                    y(p[1]).toFixed(1)
                            )
                            .join("")}
                        fill="none"
                        stroke={colors[k % colors.length]}
                        strokeWidth={2}
                        strokeLinejoin="round"
                    />
                ))}
                {ends.map((e) => (
                    <rect
                        key={e.k}
                        x={W - padR + 2}
                        y={e.y - 6}
                        width={3}
                        height={12}
                        fill={colors[e.k % colors.length]}
                    />
                ))}
                {hover !== null && (
                    <line
                        x1={x(hover)}
                        x2={x(hover)}
                        y1={padT}
                        y2={H - padB}
                        className="ean-cross"
                    />
                )}
                <rect
                    x={padL}
                    y={padT}
                    width={W - padL - padR}
                    height={H - padT - padB}
                    fill="transparent"
                    style={{ touchAction: "pan-y" }}
                    onPointerMove={(e) => {
                        const b = (e.currentTarget as any).getBoundingClientRect()
                        setHover(
                            clamp(
                                Math.round(((e.clientX - b.left) / b.width) * (n - 1)),
                                0,
                                n - 1
                            )
                        )
                    }}
                    onPointerLeave={() => setHover(null)}
                />
            </svg>
            {hover !== null && (
                <div
                    className="ean-tip"
                    style={
                        x(hover) > W / 2
                            ? { right: W - x(hover) + 10 }
                            : { left: x(hover) + 10 }
                    }
                >
                    <div className="ean-tip-d">
                        {fmtDay(dates[hover], {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                        })}
                    </div>
                    {series.map((s, k) => {
                        const p = s.points[hover - (n - s.points.length)]
                        return (
                            <div key={s.id} className="ean-tip-r">
                                <i style={{ background: colors[k % colors.length] }} />
                                <span>{s.name}</span>
                                <b>{p ? lab(p[1]) : "—"}</b>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Sample data (shown while "Data URL" is empty) — illustrative only    */
/* ------------------------------------------------------------------ */

const SAMPLE: Data = {
 "version": 1,
 "edition": {
  "date": "2026-11-17",
  "weekday": "Tuesday",
  "mode": "daily",
  "basedOn": "Monday's close (2026-11-16)"
 },
 "generated": "2026-11-16T19:18:40+00:00",
 "nextEdition": "2026-11-18T11:30:00+00:00",
 "writtenBy": "sample",
 "override": false,
 "regime": {
  "id": "risk_off",
  "label": "Risk-off",
  "score": 1.45,
  "members": [
   "vix",
   "gold",
   "usdjpy",
   "us_eq"
  ]
 },
 "lead": {
  "type": "theme",
  "id": "middle_east",
  "label": "Middle East tensions",
  "assets": [
   "brent",
   "wti",
   "gold",
   "us_eq"
  ]
 },
 "text": {
  "headline": "Gulf tensions lift oil and gold as stocks retreat",
  "tone": "A risk-off session: crude and gold rose while equities, the dollar against the yen and Bitcoin gave ground.",
  "lead": [
   "Middle East tensions set the tone. News coverage of the region ran at 2.6x its recent normal, and the markets most exposed to it moved the way such news usually moves them. [[energy|Brent crude]] rose 4.1% to $64.00, a move about twice its usual daily swing, as traders priced the risk of disruption to Gulf supply.",
   "Investors also reached for havens. [[metals|Gold]] gained 1.9% to $3,932 and the yen strengthened, with [[crypto|USD/JPY]] down 0.7% to 153.42. Gold and the yen tend to attract money when uncertainty rises, regardless of what happens to interest rates.",
   "Equities paid the price. [[markets|US large caps]] fell 1.3% and the VIX volatility index jumped 14.0%. Higher oil prices act like a tax on consumers and companies, while geopolitical risk makes investors less willing to pay for future earnings.",
   "Bond yields edged lower rather than higher: the 10-year yield slipped 3 bp to 4.10%. For now, demand for safe government bonds outweighs worries that dearer energy could push inflation up. See the [[outlook|Market Outlook]] for the wider backdrop."
  ],
  "briefs": {
   "markets": "The US 10-year yield fell 3 bp to 4.10% and the 2-year 4 bp to 3.55%, as safety buying outweighed inflation worries. Full curve on [[markets|Financial Markets]].",
   "energy": "Brent crude rose 4.1% to $64.00 and WTI 3.8% to $60.10 on Gulf supply risk; US natural gas rose 1.0%. Benchmarks and supply data on the [[energy|Energy Terminal]].",
   "crypto": "Bitcoin fell 2.2% to $94,210 with the wider risk retreat, while the yen and the Swiss franc firmed. Rates and converter on [[crypto|Crypto & Currencies]].",
   "metals": "Gold rose 1.9% to $3,932 and silver 2.4% to $48.10 on haven demand; copper slipped 0.6% to $13,530/t. Prices on the [[metals|Hard Assets Terminal]].",
   "estate": "House prices are rising in 5 of the 7 countries we track over the past year; Portugal leads at +9.1%. Country data on the [[estate|Estate Index]].",
   "corporate": "This week's top-ranked bank is East West Bank and the top company is APA Corporation. Rankings and scores on the [[corporate|Corporate Monitor]].",
   "outlook": "Our quarterly outlook still reads the backdrop as risk-on; Cybersecurity leads the five themes we follow. Details on the [[outlook|Market Outlook]].",
   "islamic": "The EB Shariah US 100 fell 1.2% to 115.50, slightly less than the unscreened market; it is +14.1% this year. More on [[islamic|Islamic Investment]]."
  },
  "watch": [
   "Whether [[energy|oil]] holds its gains if Gulf headlines calm down.",
   "Federal Reserve policy: news coverage is up, but [[markets|rates]] have not reacted yet.",
   "OPEC+ ministerial meeting (2026-11-30)."
  ]
 },
 "kpis": [
  {
   "id": "us_eq",
   "ok": true,
   "name": "US large caps (EB US 100)",
   "class": "equities",
   "page": "markets",
   "kind": "price",
   "last": 113.1976,
   "lastText": "113.20",
   "d1": -1.3,
   "d1Text": "−1.3%",
   "w1Text": "−1.2%",
   "m1Text": "−3.5%",
   "z": -1.14,
   "size": "notable",
   "asOf": "2026-11-16",
   "stale": false
  },
  {
   "id": "us10y",
   "ok": true,
   "name": "US 10-year yield",
   "class": "rates",
   "page": "markets",
   "kind": "yield",
   "last": 4.1,
   "lastText": "4.10%",
   "d1": -3.0,
   "d1Text": "−3 bp",
   "w1Text": "+4 bp",
   "m1Text": "+29 bp",
   "z": -0.54,
   "size": "quiet",
   "asOf": "2026-11-16",
   "stale": false
  },
  {
   "id": "brent",
   "ok": true,
   "name": "Brent crude",
   "class": "energy",
   "page": "energy",
   "kind": "price",
   "last": 64.0,
   "lastText": "$64.00",
   "d1": 4.1,
   "d1Text": "+4.1%",
   "w1Text": "+5.8%",
   "m1Text": "+18.5%",
   "z": 2.13,
   "size": "sharp",
   "asOf": "2026-11-16",
   "stale": false
  },
  {
   "id": "gold",
   "ok": true,
   "name": "Gold",
   "class": "metals",
   "page": "metals",
   "kind": "price",
   "last": 3931.5,
   "lastText": "$3,932",
   "d1": 1.9,
   "d1Text": "+1.9%",
   "w1Text": "−0.7%",
   "m1Text": "−5.2%",
   "z": 1.97,
   "size": "notable",
   "asOf": "2026-11-16",
   "stale": false
  },
  {
   "id": "eurusd",
   "ok": true,
   "name": "EUR/USD",
   "class": "fx",
   "page": "crypto",
   "kind": "price",
   "last": 1.0968,
   "lastText": "1.0968",
   "d1": -0.3,
   "d1Text": "−0.3%",
   "w1Text": "−0.6%",
   "m1Text": "+0.7%",
   "z": -0.71,
   "size": "quiet",
   "asOf": "2026-11-16",
   "stale": false
  },
  {
   "id": "btc",
   "ok": true,
   "name": "Bitcoin",
   "class": "crypto",
   "page": "crypto",
   "kind": "price",
   "last": 94210.0,
   "lastText": "$94,210",
   "d1": -2.2,
   "d1Text": "−2.2%",
   "w1Text": "+2.6%",
   "m1Text": "+1.5%",
   "z": -0.69,
   "size": "quiet",
   "asOf": "2026-11-16",
   "stale": false
  }
 ],
 "bars": [
  {
   "id": "us_eq",
   "name": "US large caps (EB US 100)",
   "class": "equities",
   "z": -1.14,
   "text": "−1.3%",
   "page": "markets",
   "stale": false
  },
  {
   "id": "vix",
   "name": "VIX volatility index",
   "class": "equities",
   "z": 3.18,
   "text": "+14.0%",
   "page": "markets",
   "stale": false
  },
  {
   "id": "us2y",
   "name": "US 2-year yield",
   "class": "rates",
   "z": -0.81,
   "text": "−4 bp",
   "page": "markets",
   "stale": false
  },
  {
   "id": "us10y",
   "name": "US 10-year yield",
   "class": "rates",
   "z": -0.54,
   "text": "−3 bp",
   "page": "markets",
   "stale": false
  },
  {
   "id": "us30y",
   "name": "US 30-year yield",
   "class": "rates",
   "z": -0.19,
   "text": "−1 bp",
   "page": "markets",
   "stale": false
  },
  {
   "id": "brent",
   "name": "Brent crude",
   "class": "energy",
   "z": 2.13,
   "text": "+4.1%",
   "page": "energy",
   "stale": false
  },
  {
   "id": "natgas",
   "name": "US natural gas (Henry Hub)",
   "class": "energy",
   "z": 0.29,
   "text": "+1.0%",
   "page": "energy",
   "stale": false
  },
  {
   "id": "gold",
   "name": "Gold",
   "class": "metals",
   "z": 1.97,
   "text": "+1.9%",
   "page": "metals",
   "stale": false
  },
  {
   "id": "silver",
   "name": "Silver",
   "class": "metals",
   "z": 1.23,
   "text": "+2.4%",
   "page": "metals",
   "stale": false
  },
  {
   "id": "copper",
   "name": "Copper",
   "class": "metals",
   "z": -0.54,
   "text": "−0.6%",
   "page": "metals",
   "stale": false
  },
  {
   "id": "eurusd",
   "name": "EUR/USD",
   "class": "fx",
   "z": -0.71,
   "text": "−0.3%",
   "page": "crypto",
   "stale": false
  },
  {
   "id": "usdjpy",
   "name": "USD/JPY",
   "class": "fx",
   "z": -1.35,
   "text": "−0.7%",
   "page": "crypto",
   "stale": false
  },
  {
   "id": "btc",
   "name": "Bitcoin",
   "class": "crypto",
   "z": -0.69,
   "text": "−2.2%",
   "page": "crypto",
   "stale": false
  },
  {
   "id": "eth",
   "name": "Ether",
   "class": "crypto",
   "z": -0.79,
   "text": "−2.2%",
   "page": "crypto",
   "stale": false
  }
 ],
 "context": {
  "title": "One month in context",
  "series": [
   {
    "id": "brent",
    "name": "Brent crude",
    "unit": "%",
    "page": "energy",
    "points": [
     [
      "2026-10-15",
      0.0
     ],
     [
      "2026-10-16",
      -3.75
     ],
     [
      "2026-10-19",
      -2.2
     ],
     [
      "2026-10-20",
      0.11
     ],
     [
      "2026-10-21",
      -0.43
     ],
     [
      "2026-10-22",
      -1.27
     ],
     [
      "2026-10-23",
      2.18
     ],
     [
      "2026-10-26",
      -1.05
     ],
     [
      "2026-10-27",
      -0.22
     ],
     [
      "2026-10-28",
      4.13
     ],
     [
      "2026-10-29",
      2.39
     ],
     [
      "2026-10-30",
      3.67
     ],
     [
      "2026-11-02",
      7.19
     ],
     [
      "2026-11-03",
      6.95
     ],
     [
      "2026-11-04",
      8.03
     ],
     [
      "2026-11-05",
      9.79
     ],
     [
      "2026-11-06",
      8.0
     ],
     [
      "2026-11-09",
      7.83
     ],
     [
      "2026-11-10",
      8.39
     ],
     [
      "2026-11-11",
      10.01
     ],
     [
      "2026-11-12",
      9.94
     ],
     [
      "2026-11-13",
      9.55
     ],
     [
      "2026-11-16",
      14.04
     ]
    ]
   },
   {
    "id": "gold",
    "name": "Gold",
    "unit": "%",
    "page": "metals",
    "points": [
     [
      "2026-10-15",
      0.0
     ],
     [
      "2026-10-16",
      0.04
     ],
     [
      "2026-10-19",
      -1.61
     ],
     [
      "2026-10-20",
      -1.4
     ],
     [
      "2026-10-21",
      -1.24
     ],
     [
      "2026-10-22",
      -2.73
     ],
     [
      "2026-10-23",
      -3.0
     ],
     [
      "2026-10-26",
      -3.34
     ],
     [
      "2026-10-27",
      -2.85
     ],
     [
      "2026-10-28",
      -2.19
     ],
     [
      "2026-10-29",
      -2.23
     ],
     [
      "2026-10-30",
      -3.15
     ],
     [
      "2026-11-02",
      -3.3
     ],
     [
      "2026-11-03",
      -3.37
     ],
     [
      "2026-11-04",
      -2.59
     ],
     [
      "2026-11-05",
      -2.28
     ],
     [
      "2026-11-06",
      -3.05
     ],
     [
      "2026-11-09",
      -4.5
     ],
     [
      "2026-11-10",
      -4.89
     ],
     [
      "2026-11-11",
      -5.66
     ],
     [
      "2026-11-12",
      -6.82
     ],
     [
      "2026-11-13",
      -6.94
     ],
     [
      "2026-11-16",
      -5.17
     ]
    ]
   }
  ],
  "note": "Change since the first day shown: % for prices, basis points for yields."
 },
 "themes": [
  {
   "id": "middle_east",
   "label": "Middle East tensions",
   "status": "confirmed",
   "spike": 2.6,
   "direction": null,
   "consistent": [
    "brent",
    "wti",
    "gold",
    "us_eq",
    "usdjpy",
    "usdchf",
    "vix"
   ],
   "against": [],
   "headlines": [],
   "newsSource": "GDELT"
  },
  {
   "id": "fed",
   "label": "Federal Reserve policy",
   "status": "news_only",
   "spike": 1.7,
   "direction": "a more dovish Fed",
   "consistent": [
    "us2y",
    "gold"
   ],
   "against": [
    "us_eq"
   ],
   "headlines": [
    {
     "title": "Sample headline about Federal Reserve policy",
     "url": "",
     "source": "example.org",
     "date": "2026-11-16"
    }
   ],
   "newsSource": "GDELT"
  }
 ],
 "pages": {
  "markets": "/market-data",
  "energy": "/energy-terminal",
  "crypto": "/crypto-currencies",
  "metals": "/hard-assets-terminal",
  "estate": "/estate-index",
  "corporate": "/corporate-monitor",
  "outlook": "/market-outlook",
  "islamic": "/islamic-investment"
 },
 "sources": "Economic Bearings pages and engines (Financial Markets, Energy Terminal, Crypto & Currencies, Hard Assets, Estate Index, Corporate Monitor, Market Outlook, Islamic Investment). Underlying data: FRED, ECB (Frankfurter), CoinGecko, COMEX/NYMEX and LME via EB Metals, CEII, OECD. News volume and headlines: GDELT or Google News; each headline links to the original article.",
 "sample": true
}

/* ------------------------------------------------------------------ */
/* Data hook                                                           */
/* ------------------------------------------------------------------ */

function useData(url: string) {
    const [data, setData] = React.useState<Data | null>(() =>
        url ? readStore("data:" + url)?.json || null : SAMPLE
    )
    const [status, setStatus] = React.useState<"sample" | "loading" | "ok" | "error">(
        url ? "loading" : "sample"
    )
    React.useEffect(() => {
        if (!url) {
            setData(SAMPLE)
            setStatus("sample")
            return
        }
        let alive = true
        const saved = readStore("data:" + url)
        if (saved?.json) setData(saved.json)
        const load = () =>
            fetch(url, { cache: "no-cache" })
                .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
                .then((j) => {
                    if (!alive || !j || !j.text || !j.edition) throw 0
                    setData(j)
                    setStatus("ok")
                    writeStore("data:" + url, { at: Date.now(), json: j })
                })
                .catch(() => alive && setStatus(saved?.json ? "ok" : "error"))
        load()
        const id = setInterval(load, 30 * 60 * 1000)
        return () => {
            alive = false
            clearInterval(id)
        }
    }, [url])
    return { data, status, setData }
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

const SECTION_ORDER = [
    "markets",
    "energy",
    "crypto",
    "metals",
    "estate",
    "corporate",
    "outlook",
    "islamic",
]

export default function TheAnalyst(props: any) {
    const clean = (o: any): Record<string, any> =>
        Object.fromEntries(
            Object.entries(o || {}).filter(
                ([, v]) => v !== undefined && v !== null && v !== ""
            )
        )
    const p: any = { ...DEFAULTS, ...clean(props) }
    const tx: Record<string, string> = { ...DEF_TEXTS, ...clean(p.texts) }
    const links: Record<string, string> = { ...DEF_LINKS, ...clean(p.links) }
    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    const rootRef = React.useRef<HTMLDivElement>(null)
    const W = useWidth(rootRef)
    const phone = W < 600
    const url = String(p.dataUrl || "").trim()
    const { data, status, setData } = useData(url)
    const D: Data = data || SAMPLE
    // no edition could be loaded: the live site says so instead of showing sample text
    const missing = !data && status === "error" && !isCanvas

    const [now, setNow] = React.useState(() => Date.now())
    React.useEffect(() => {
        if (isCanvas) return
        const id = setInterval(() => setNow(Date.now()), 60000)
        return () => clearInterval(id)
    }, [isCanvas])

    // previous editions (docs/analyst/index.json next to the Data URL)
    const base = url ? url.replace(/[^/]+$/, "") + "analyst/" : ""
    const [editions, setEditions] = React.useState<string[]>([])
    const [picked, setPicked] = React.useState("")
    React.useEffect(() => {
        if (!base || !p.showArchive) return
        fetch(base + "index.json", { cache: "no-cache" })
            .then((r) => r.json())
            .then((j) => setEditions((j?.editions || []).slice(0, 60)))
            .catch(() => {})
    }, [base, p.showArchive])
    const pick = (d: string) => {
        setPicked(d)
        if (!d) {
            const s = readStore("data:" + url)
            if (s?.json) setData(s.json)
            return
        }
        fetch(base + d + ".json")
            .then((r) => r.json())
            .then((j) => j && j.text && setData(j))
            .catch(() => {})
    }

    const href = (key: string) => {
        const v = links[key] ?? D.pages?.[key] ?? ""
        return v ? String(v) : ""
    }
    const pageName = (key: string) => tx["page_" + key] || key

    const nextT = Date.parse(D.nextEdition || "")
    const statusText =
        status === "sample"
            ? tx.sample
            : status === "error" && !data
              ? isCanvas
                  ? tx.sample
                  : tx.unavailable
              : picked
                ? tx.archived
                : tx.live

    /* ---------- pieces ---------- */
    const kpis = p.showKpis && (D.kpis || []).length > 0 && (
        <div className="ean-kpis">
            {D.kpis.map((m) => (
                <a
                    key={m.id}
                    className="ean-kpi"
                    href={href(m.page || "") || undefined}
                    target="_blank"
                    rel="noopener"
                >
                    <div className="ean-kl">{tx["kpi_" + m.id] || m.name}</div>
                    <div className="ean-kv">{m.lastText}</div>
                    <div className="ean-ks">
                        <Pct m={m} />{" "}
                        <span className="ean-mut">
                            {m.asOf && D.edition?.basedOn && m.asOf < (D.edition.basedOn.match(/\d{4}-\d{2}-\d{2}/) || [""])[0]
                                ? tx.onDate.replace("{d}", fmtDay(m.asOf, { month: "short", day: "numeric" }))
                                : tx.today}
                        </span>
                    </div>
                </a>
            ))}
        </div>
    )

    const lead = (
        <article className="ean-lead">
            {(D.text.lead || []).map((para, i) => (
                <p key={i} className={i === 0 ? "ean-first" : ""}>
                    <Rich text={para} href={href} />
                </p>
            ))}
            {D.edition?.basedOn && (
                <p className="ean-based">{tx.basedOn.replace("{d}", D.edition.basedOn)}</p>
            )}
        </article>
    )

    const briefs = (
        <Panel title={tx.briefsTitle} note={tx.briefsNote}>
            <ul className="ean-briefs">
                {SECTION_ORDER.filter((k) => D.text.briefs?.[k]).map((k) => (
                    <li key={k}>
                        <a className="ean-bk" href={href(k) || undefined} target="_blank" rel="noopener">
                            {pageName(k)}
                            <span aria-hidden="true"> →</span>
                        </a>
                        <span className="ean-bt">
                            <Rich text={D.text.briefs[k]} href={href} />
                        </span>
                    </li>
                ))}
            </ul>
        </Panel>
    )

    // The weekly cartoon: shown only when an image is set in Framer, always at its own
    // proportions (never cropped or stretched). On wide screens the page is balanced
    // like a printed newspaper: the cartoon and the side blocks go where both columns end
    // closest to the same line, then the shorter column spreads its spacing evenly.
    const cSrc =
        typeof p.cartoonImage === "string"
            ? p.cartoonImage
            : p.cartoonImage?.src || ""
    const cSet = typeof p.cartoonImage === "object" ? p.cartoonImage?.srcSet || "" : ""
    const lRef = React.useRef<HTMLDivElement>(null)
    const rRef = React.useRef<HTMLDivElement>(null)
    const blk = React.useRef<Record<string, HTMLDivElement | null>>({})
    const [ratio, setRatio] = React.useState(1.4)
    const [moveL, setMoveL] = React.useState<string[]>([])
    const [cSide, setCSide] = React.useState<"left" | "right">("left")
    const [just, setJust] = React.useState<"" | "left" | "right">("")
    const [fill, setFill] = React.useState<{ side: string; rows: number }>({ side: "", rows: 0 })
    const ROWH = 27
    const decided = React.useRef("")
    const [cLoaded, setCLoaded] = React.useState(0)
    // The radar always shows the 4 themes that matter most today: themes moving markets
    // first, then those heating up in the news, then the most covered of the rest.
    const ORDER: Record<string, number> = { confirmed: 0, news_only: 1, market_only: 2, quiet: 3 }
    const radarRows = (D.themes || [])
        .filter((t) => t.status !== "quiet" || (t.headlines || []).some((x) => x.url))
        .sort((a, b) => (ORDER[a.status] ?? 3) - (ORDER[b.status] ?? 3) || (b.spike || 0) - (a.spike || 0))

    // "Also in the news": today's other headlines (not already shown in the radar),
    // used to fill the shorter column so both columns end on the same line.
    const shownInRadar = new Set(
        radarRows
            .slice(0, 4)
            .map((t) => ((t.headlines || []).find((x) => x.url)?.title || "").toLowerCase())
    )
    const extraNews = (D.news || []).filter((n) => n.url && !shownInRadar.has(n.title.toLowerCase()))
    const MAXROWS = extraNews.length
    const capH = p.cartoonCaption || p.cartoonCredit ? 50 : 0
    React.useLayoutEffect(() => {
        const l = lRef.current
        const r = rRef.current
        if (!l || !r) return
        const id = setTimeout(() => {
            const grid = l.closest(".ean-grid") as HTMLElement | null
            grid?.classList.add("ean-measure")
            const GAP = 24
            const kids = (el: HTMLElement) =>
                Array.from(el.children).map((c) => (c as HTMLElement).offsetHeight)
            const sum = (xs: number[]) =>
                xs.reduce((a, x) => a + x, 0) + GAP * Math.max(0, xs.length - 1)
            const h = (k: string) => (blk.current[k]?.offsetHeight || 0) + GAP
            const cart = (side: string) =>
                cSrc ? ((side === "left" ? l : r).offsetWidth / ratio) + 46 + capH + GAP : 0
            const lNow = sum(kids(l)) + (cSrc && cSide === "left" ? cart("left") : 0)
            const rNow = sum(kids(r)) + (cSrc && cSide === "right" ? cart("right") : 0)
            const key = [W, D.generated, cSrc, ratio.toFixed(2)].join("|")
            let L = lNow
            let R = rNow
            if (decided.current !== key) {
                decided.current = key
                const lb = lNow - moveL.reduce((a, k) => a + h(k), 0) - (cSrc && cSide === "left" ? cart("left") : 0)
                const rb = rNow - ["watch", "radar"].filter((k) => !moveL.includes(k)).reduce((a, k) => a + h(k), 0) - (cSrc && cSide === "right" ? cart("right") : 0)
                let best: any = null
                for (const m of [[], ["watch", "radar"]]) // the two stay together, watch first
                    for (const s of cSrc ? ["left", "right"] : ["left"]) {
                        const LL = lb + m.reduce((a, k) => a + h(k), 0) + (s === "left" ? cart("left") : 0)
                        const RR = rb + ["watch", "radar"].filter((k) => !m.includes(k)).reduce((a, k) => a + h(k), 0) + (s === "right" ? cart("right") : 0)
                        const d = Math.abs(LL - RR)
                        if (!best || d < best.d - 16) best = { m, s, d, LL, RR }
                    }
                if (best) {
                    if (best.m.join() !== moveL.join()) setMoveL(best.m)
                    if (best.s !== cSide) setCSide(best.s)
                    L = best.LL
                    R = best.RR
                }
            }
            // real heights (the stacks stretch, so their children are summed instead)
            const real = (stack: HTMLElement) => {
                const col = stack.parentElement as HTMLElement
                let tot = sum(kids(stack))
                for (const c of Array.from(col.children) as HTMLElement[])
                    if (c !== stack && !c.dataset.filler) tot += c.offsetHeight + GAP
                return tot
            }
            const RL = real(l)
            const RRr = real(r)
            const gap = Math.abs(RL - RRr)
            const side = RL < RRr ? "left" : "right"
            const rows = Math.min(MAXROWS, Math.floor((gap - GAP - 46) / ROWH))
            const nf = rows >= 1 ? { side, rows } : { side: "", rows: 0 }
            setFill((f) => (f.side === nf.side && f.rows === nf.rows ? f : nf))
            // what is left is spread over the rows of the briefs / the moves chart,
            // only while it stays discreet (a few pixels per row)
            const left = gap - (nf.rows ? GAP + 46 + nf.rows * ROWH : 0)
            const absorbRows = side === "left" ? 8 : 14
            const nj = left > 2 && left / absorbRows <= 14 ? side : ""
            setJust((j) => (j === nj ? j : (nj as any)))
            grid?.classList.remove("ean-measure")
        }, 80)
        return () => clearTimeout(id)
    }, [W, data, cSrc, ratio, moveL, cSide, cLoaded, fill.rows, fill.side])
    const cartoon = cSrc ? (
        <Panel title={p.cartoonTitle || tx.cartoonTitle} note={p.cartoonDate || ""}>
            <figure className="ean-cart">
                <img
                    src={cSrc}
                    srcSet={cSet || undefined}
                    sizes="(min-width: 980px) 60vw, 100vw"
                    alt={p.cartoonAlt || p.cartoonCaption || p.cartoonTitle || tx.cartoonTitle}
                    decoding="async"
                    onLoad={(e) => {
                        const im = e.currentTarget
                        if (im.naturalWidth && im.naturalHeight)
                            setRatio(im.naturalWidth / im.naturalHeight)
                        setCLoaded((n) => n + 1)
                    }}
                />
                {(p.cartoonCaption || p.cartoonCredit) && (
                    <figcaption>
                        {p.cartoonCaption}
                        {p.cartoonCredit && <small>{p.cartoonCredit}</small>}
                    </figcaption>
                )}
            </figure>
        </Panel>
    ) : null

    const bars = (D.bars || []).filter((b) => !b.stale)
    const chart1 = bars.length > 0 && (
        <Panel title={tx.barsTitle} note={tx.barsNote}>
            <MoveBars rows={bars} href={href} />
        </Panel>
    )

    const ctx = D.context?.series || []
    const colors = [p.link, p.midColor, p.muted]
    const chart2 = ctx.length > 0 && (
        <Panel title={tx.contextTitle} note={tx.contextNote}>
            <div className="ean-legend">
                {ctx.map((s, k) => (
                    <a key={s.id} href={href(s.page) || undefined} target="_blank" rel="noopener">
                        <i style={{ background: colors[k % colors.length] }} />
                        {s.name}
                    </a>
                ))}
            </div>
            <ContextChart
                series={ctx}
                colors={colors}
                height={phone ? 190 : p.chartHeight}
            />
        </Panel>
    )

    const watch = (D.text.watch || []).length > 0 && (
        <Panel title={tx.watchTitle}>
            <ol className="ean-watch">
                {D.text.watch.map((w, i) => (
                    <li key={i}>
                        <Rich text={w} href={href} />
                    </li>
                ))}
            </ol>
        </Panel>
    )

    const radar = p.showRadar && radarRows.length > 0 && (
        <Panel title={tx.radarTitle} note={tx.radarNote}>
            <ul className="ean-radar">
                {radarRows.slice(0, 4).map((t) => {
                    const h = (t.headlines || []).find((x) => x.url)
                    return (
                        <li key={t.id}>
                            <div className="ean-rh">
                                <b>{t.label}</b>
                                <span className={"ean-chip is-" + t.status}>
                                    {tx["st_" + t.status] || t.status}
                                </span>
                            </div>
                            {isNum(t.spike) && (
                                <div className="ean-rm">
                                    <span className="ean-meter">
                                        <i
                                            style={{
                                                width: clamp((t.spike / 4) * 100, 4, 100) + "%",
                                            }}
                                        />
                                    </span>
                                    <small>
                                        {tx.coverage.replace("{x}", t.spike.toFixed(1))}
                                    </small>
                                </div>
                            )}
                            {h && (
                                <a
                                    className="ean-rl"
                                    href={h.url}
                                    target="_blank"
                                    rel="noopener nofollow"
                                >
                                    {h.title}
                                    <small> · {h.source}</small>
                                </a>
                            )}
                        </li>
                    )
                })}
            </ul>
        </Panel>
    )

    const wide = W >= 980
    const filler = (s: string) =>
        fill.side === s && fill.rows > 0 ? (
            <div data-filler="1">
                <Panel title={tx.alsoTitle} note={tx.alsoNote}>
                    <ul className="ean-also">
                        {extraNews.slice(0, fill.rows).map((n, i) => (
                            <li key={i}>
                                <a href={n.url} target="_blank" rel="noopener nofollow" title={n.title}>
                                    {n.title}
                                </a>
                                <small>{n.source}</small>
                            </li>
                        ))}
                    </ul>
                </Panel>
            </div>
        ) : null
    const wb = (k: string, node: React.ReactNode) =>
        node ? <div key={k} ref={(e) => (blk.current[k] = e)}>{node}</div> : null
    const body = wide ? (
        <div className="ean-grid ean-paper">
            <div className={"ean-col" + (just === "left" ? " ean-just" : "")}>
                <div ref={lRef} className="ean-col ean-stack">
                    {lead}
                    <div className="ean-grow">{briefs}</div>
                    {moveL.includes("watch") && wb("watch", watch)}
                    {moveL.includes("radar") && wb("radar", radar)}
                </div>
                {cSide === "left" && cartoon}
                {filler("left")}
            </div>
            <div className={"ean-col" + (just === "right" ? " ean-just" : "")}>
                <div ref={rRef} className="ean-col ean-stack">
                    <div className="ean-grow">{chart1}</div>
                    {chart2}
                    {!moveL.includes("watch") && wb("watch", watch)}
                    {!moveL.includes("radar") && wb("radar", radar)}
                </div>
                {cSide === "right" && cartoon}
                {filler("right")}
            </div>
        </div>
    ) : (
        <div className="ean-col">
            {lead}
            {chart1}
            {chart2}
            {briefs}
            {cartoon}
            {watch}
            {radar}
        </div>
    )

    const vars = {
        "--bg": p.background,
        "--ink": p.ink,
        "--mute": p.muted,
        "--rule": p.rule,
        "--strong": p.strongRule,
        "--link": p.link,
        "--up": p.upColor,
        "--dn": p.downColor,
        "--mid": p.midColor,
        "--maxw": Math.max(320, Number(p.maxWidth) || 1200) + "px",
        "--pad":
            (phone ? 18 : !wide ? Math.max(28, Number(p.padding) || 0) : Number(p.padding) || 0) +
            "px",
        "--t0": Math.max(18, Number(p.headlineSize) || 34) + "px",
        "--t1": Math.max(14, Number(p.titleSize) || 26) + "px",
        "--t2": Math.max(12, Number(p.sectionTitleSize) || 18) + "px",
        "--body": Math.max(13, Number(p.bodySize) || 17) + "px",
        "--row": Math.max(11, Number(p.rowSize) || 13.5) + "px",
        "--kv": Math.max(14, Number(p.kpiSize) || 22) + "px",
        "--fh":
            fam(p.headingFont, 'Georgia,"Times New Roman",serif') ||
            '"Libre Caslon Text",Georgia,"Times New Roman",serif',
        "--fb":
            fam(p.bodyFont, '"Helvetica Neue",Arial,sans-serif') ||
            'Inter,"Helvetica Neue",Arial,sans-serif',
    } as React.CSSProperties

    return (
        <div
            ref={rootRef}
            className={"ean" + (phone ? " ean-phone" : !wide ? " ean-mid" : "")}
            style={vars}
        >
            <style>{CSS}</style>
            <div className="ean-in">
                {p.showHeader && (
                    <header className="ean-mast">
                        <div>
                            {tx.kicker && <div className="ean-kick">{tx.kicker}</div>}
                            <h1>{tx.title}</h1>
                            {tx.subtitle && <p className="ean-sub">{tx.subtitle}</p>}
                        </div>
                        <div className="ean-stamp">
                            <span
                                className={
                                    "ean-dot " +
                                    (status === "sample"
                                        ? "is-sample"
                                        : status === "ok" && !picked
                                          ? "is-live"
                                          : "")
                                }
                            />
                            <b>{statusText}</b>
                            <span>
                                {fmtDay(D.edition?.date, {
                                    weekday: "long",
                                    month: "long",
                                    day: "numeric",
                                    year: "numeric",
                                })}
                            </span>
                            {isNum(nextT) && !picked && !!data && status !== "sample" && (
                                <span>{tx.nextIn.replace("{t}", fmtLeft(nextT - now))}</span>
                            )}
                            {p.showArchive && editions.length > 1 && (
                                <select
                                    className="ean-arch"
                                    value={picked}
                                    onChange={(e) => pick(e.target.value)}
                                    aria-label={tx.archive}
                                >
                                    <option value="">{tx.latest}</option>
                                    {editions.slice(1).map((d) => (
                                        <option key={d} value={d}>
                                            {fmtDay(d, {
                                                month: "short",
                                                day: "numeric",
                                                year: "numeric",
                                            })}
                                        </option>
                                    ))}
                                </select>
                            )}
                        </div>
                    </header>
                )}

                {missing ? (
                    <p className="ean-missing">{tx.missing}</p>
                ) : (
                <>
                <div className="ean-top">
                    <div className="ean-tag">
                        {D.regime?.label && (
                            <span className={"ean-reg is-" + (D.regime.id || "")}>
                                {D.regime.label}
                            </span>
                        )}
                    </div>
                    <h2 className="ean-head">{D.text.headline}</h2>
                    {D.text.tone && <p className="ean-tone">{D.text.tone}</p>}
                </div>

                {kpis}
                <div className="ean-body">{body}</div>
                </>
                )}

                {p.showFooter && (
                    <footer className="ean-foot">
                        <p>
                            <b>{tx.footBold}</b> {tx.footText}
                        </p>
                        <details>
                            <summary>{tx.methodTitle}</summary>
                            <p>{tx.methodIntro}</p>
                            <ul className="ean-meth">
                                {[1, 2, 3, 4].map((i) => (
                                    <li key={i}>
                                        <b>{tx["method" + i + "Title"]}:</b> {tx["method" + i]}
                                    </li>
                                ))}
                            </ul>
                            <p className="ean-tagline">{tx.methodTagline}</p>
                        </details>
                        <details>
                            <summary>{tx.sourcesTitle}</summary>
                            <p>{D.sources}</p>
                        </details>
                    </footer>
                )}
            </div>
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Styles (same system as EB Islamic Investment)                        */
/* ------------------------------------------------------------------ */

const CSS = `
.ean{width:100%;background:var(--bg);color:var(--ink);font-family:var(--fb);font-size:var(--row);line-height:1.4;box-sizing:border-box;padding:var(--pad);-webkit-font-smoothing:antialiased}
.ean *{box-sizing:border-box}
.ean-in{max-width:var(--maxw);margin:0 auto;display:flex;flex-direction:column;gap:20px}
.ean a{color:inherit;text-decoration:none}
.ean-up{color:var(--up)} .ean-dn{color:var(--dn)} .ean-mut{color:var(--mute)}
.ean-mast{display:flex;justify-content:space-between;align-items:baseline;gap:8px 16px;flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:12px}
.ean-kick{font-size:9.5px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin-bottom:4px}
.ean-mast h1{font-family:var(--fh);font-weight:400;font-size:var(--t1);line-height:1.15;margin:0;letter-spacing:.04em}
.ean-sub{margin:4px 0 0;color:var(--mute);font-size:12px;line-height:1.5;max-width:640px}
.ean-stamp{display:flex;align-items:center;flex-wrap:wrap;gap:4px 10px;font-size:11px;color:var(--mute)}
.ean-stamp b{color:var(--ink);font-weight:600}
.ean-dot{width:6px;height:6px;border-radius:50%;display:inline-block;background:var(--mute)}
.ean-dot.is-live{background:var(--up);animation:ean-blink 1.8s ease-in-out infinite}
.ean-dot.is-sample{background:#C98B00}
@keyframes ean-blink{0%,100%{opacity:1}50%{opacity:.3}}
@media (prefers-reduced-motion:reduce){.ean-dot.is-live{animation:none}}
.ean-arch{border:1px solid var(--rule);background:transparent;color:var(--link);font:inherit;font-size:11px;padding:2px 4px}
.ean-top{display:flex;flex-direction:column;gap:8px;max-width:860px}
.ean-tag{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;font-size:11px}
.ean-reg{font-size:9.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--ink);border-bottom:2px solid var(--ink);padding-bottom:1px}
.ean-reg.is-risk_off,.ean-reg.is-growth{border-color:var(--dn)}
.ean-reg.is-risk_on{border-color:var(--up)}
.ean-reg.is-inflation,.ean-reg.is-usd_up,.ean-reg.is-usd_down{border-color:var(--mid)}
.ean-head{font-family:var(--fh);font-weight:400;font-size:var(--t0);line-height:1.1;margin:0;text-wrap:balance;letter-spacing:-.005em}
.ean-tone{font-family:var(--fh);font-style:italic;font-size:calc(var(--body) + 1px);line-height:1.45;color:var(--mute);margin:0;max-width:62ch}
.ean-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));border-top:1px solid var(--strong);border-bottom:1px solid var(--rule)}
.ean-kpi{box-shadow:inset -1px 0 0 var(--rule);padding:11px 16px;display:flex;flex-direction:column;gap:3px;min-width:0}
.ean-kpi:first-child{padding-left:0}
.ean-kpi:last-child{box-shadow:none}
.ean-kpi:hover .ean-kl{color:var(--link)}
.ean-kl{font-size:9.5px;font-weight:500;letter-spacing:.05em;text-transform:uppercase;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ean-kv{font-family:var(--fh);font-size:var(--kv);line-height:1.15;font-variant-numeric:tabular-nums lining-nums}
.ean-ks{font-size:11.5px;font-variant-numeric:tabular-nums}
.ean-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);gap:22px 40px;align-items:start}
.ean-col{display:flex;flex-direction:column;gap:24px;min-width:0}
.ean-lead p{font-family:var(--fh);font-size:var(--body);line-height:1.66;margin:0 0 18px;max-width:68ch}
.ean-lead p.ean-first::first-letter{font-size:3.1em;float:left;line-height:.9;padding:4px 8px 0 0}
.ean a.ean-a{color:var(--link);border-bottom:1px solid color-mix(in srgb,var(--link) 35%,transparent)}
.ean a.ean-a:hover{border-bottom-color:var(--link)}
.ean-lead p.ean-based{font-family:var(--fb);font-size:11.5px;line-height:1.4;color:var(--mute);margin:-4px 0 0}
.ean-panel{border-top:1px solid var(--strong);min-width:0}
.ean-ph{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;padding:9px 0 8px}
.ean-ph h3{margin:0;font-family:var(--fh);font-weight:400;font-size:var(--t2);line-height:1.2}
.ean-note{font-size:11px;color:var(--mute)}
.ean-empty{display:flex;align-items:center;justify-content:center;color:var(--mute);font-size:12px}
/* briefs */
.ean-briefs{list-style:none;margin:0;padding:0}
.ean-briefs li{display:grid;grid-template-columns:150px minmax(0,1fr);gap:4px 16px;padding:9px 0;border-top:1px solid var(--rule)}
.ean-briefs li:first-child{border-top:0}
.ean-bk{font-family:var(--fh);font-size:15px;color:var(--ink)!important}
.ean-bk span{color:var(--link)}
.ean-bk:hover{color:var(--link)!important}
.ean-bt{font-size:14.5px;line-height:1.55}
.ean-phone .ean-briefs li{grid-template-columns:minmax(0,1fr)}
/* chart 1 */
.ean-mb{display:flex;flex-direction:column}
.ean-mbr{display:grid;grid-template-columns:minmax(90px,1.1fr) minmax(80px,1.6fr) 66px;gap:10px;align-items:center;padding:4px 0;border-top:1px solid var(--rule)}
.ean-mbr:first-child{border-top:0}
.ean-mbn{font-family:var(--fh);font-size:13.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ean-mbn:hover{color:var(--link)}
.ean-mbt{position:relative;height:10px}
.ean-mbt em{position:absolute;left:25%;right:25%;top:0;bottom:0;background:color-mix(in srgb,var(--rule) 45%,transparent)}
.ean-mbt::after{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--strong)}
.ean-mbt i{position:absolute;top:2px;height:6px}
.ean-mbv{text-align:right;font-family:var(--fh);font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap}
.ean-mbs{display:grid;grid-template-columns:minmax(90px,1.1fr) minmax(80px,1.6fr) 66px;gap:10px;font-size:10px;color:var(--mute);padding-top:4px}
.ean-mbs span:first-child{grid-column:2;grid-row:1;justify-self:start}
.ean-mbs span:nth-child(2){grid-column:2;grid-row:1;justify-self:center}
.ean-mbs span:last-child{grid-column:2;grid-row:1;justify-self:end}
/* chart 2 */
.ean-legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;padding:0 0 4px}
.ean-legend a{display:inline-flex;align-items:center;gap:6px}
.ean-legend a:hover{color:var(--link)}
.ean-legend i{width:12px;height:2px;display:inline-block}
.ean-chart svg{display:block;overflow:visible}
.ean .ean-gl{stroke:var(--rule);stroke-width:1}
.ean .ean-zero{stroke:var(--strong);stroke-width:1;stroke-dasharray:3 3}
.ean .ean-cross{stroke:var(--mute);stroke-width:1}
.ean .ean-axis{fill:var(--mute);font-size:10px;font-family:var(--fb);font-variant-numeric:tabular-nums}
.ean-tip{position:absolute;top:8px;background:var(--bg);border:1px solid var(--rule);border-top:2px solid var(--ink);padding:7px 9px;font-size:12px;pointer-events:none;min-width:160px;z-index:3}
.ean-tip-d{font-weight:600;margin-bottom:3px}
.ean-tip-r{display:flex;align-items:center;gap:6px;padding:1px 0}
.ean-tip-r i{width:8px;height:8px;flex:none}
.ean-tip-r span{flex:1;color:var(--mute)}
.ean-tip-r b{font-variant-numeric:tabular-nums}
/* watch & radar */
.ean-watch{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:7px;font-size:14.5px;line-height:1.55}
.ean-watch li::marker{font-family:var(--fh);color:var(--mute)}
.ean-radar{list-style:none;margin:0;padding:0}
.ean-radar li{display:flex;flex-direction:column;gap:4px;padding:8px 0;border-top:1px solid var(--rule)}
.ean-radar li:first-child{border-top:0}
.ean-rh{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.ean-rh b{font-family:var(--fh);font-weight:400;font-size:14px}
.ean-chip{font-size:9.5px;letter-spacing:.05em;text-transform:uppercase;white-space:nowrap;color:var(--mute)}
.ean-chip.is-confirmed{color:var(--dn)}
.ean-chip.is-news_only{color:var(--mid)}
.ean-rm{display:flex;align-items:center;gap:10px}
.ean-rm small{font-size:10.5px;color:var(--mute);white-space:nowrap}
.ean-meter{position:relative;flex:1;height:7px}
.ean-meter::before{content:"";position:absolute;left:0;right:0;top:3px;height:1px;background:var(--rule)}
.ean-meter i{position:absolute;left:0;top:3px;height:1px;background:var(--ink)}
.ean-meter i::after{content:"";position:absolute;right:-2.5px;top:-2px;width:5px;height:5px;border-radius:50%;background:var(--ink)}
.ean-rl{font-size:13.5px;line-height:1.45;color:var(--ink)}
.ean-rl:hover{color:var(--link)}
.ean-rl small{color:var(--mute);font-size:10.5px}
/* weekly cartoon */
.ean-cart{margin:4px 0 0}
.ean-cart img{display:block;width:100%;height:auto;border:1px solid var(--rule)}
.ean-paper{align-items:stretch}
.ean-just{justify-content:space-between}
/* vertical justification: the rows of the briefs (left) and of the moves chart (right)
   share any leftover height, so the gap is spread over many small steps */
.ean-just>.ean-stack{flex:1}
.ean-just .ean-grow{flex:1;display:flex;flex-direction:column}
.ean-just .ean-grow>section{flex:1;display:flex;flex-direction:column}
.ean-just .ean-grow .ean-briefs,.ean-just .ean-grow .ean-mb{flex:1;display:flex;flex-direction:column;justify-content:space-between}
.ean-measure .ean-stack,.ean-measure .ean-grow,.ean-measure .ean-grow>section,.ean-measure .ean-briefs,.ean-measure .ean-mb{flex:none!important}
.ean-grow .ean-briefs li{align-items:center}
.ean-also{list-style:none;margin:0;padding:0}
.ean-also li{height:27px;display:flex;align-items:center;gap:10px;border-top:1px solid var(--rule);font-size:12.5px;min-width:0}
.ean-also li:first-child{border-top:0}
.ean-also a{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ean-also a:hover{color:var(--link)}
.ean-also small{flex:none;font-size:10.5px;color:var(--mute);max-width:35%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ean-cart figcaption{font-family:var(--fh);font-style:italic;font-size:14px;line-height:1.45;margin-top:8px;display:flex;flex-direction:column;gap:2px}
.ean-cart small{font-family:var(--fb);font-style:normal;font-size:10.5px;color:var(--mute)}
/* footer */
.ean-foot{border-top:1px solid var(--rule);padding-top:10px;font-size:11px;color:var(--mute)}
.ean-foot p{margin:0 0 6px}
.ean-foot b{color:var(--ink);font-weight:600}
.ean-foot summary{cursor:pointer;color:var(--link);margin:4px 0}
.ean-tagline{font-family:var(--fh);font-style:italic;color:var(--ink);font-size:13px}
.ean-meth b{color:var(--ink);font-weight:600}
.ean-meth{margin:4px 0 8px;padding-left:16px;display:flex;flex-direction:column;gap:3px;line-height:1.5}
.ean-missing{font-family:var(--fh);font-size:var(--body);color:var(--mute);padding:40px 0;margin:0}
.ean-phone .ean-mbs span:nth-child(2){display:none}
.ean-phone .ean-kpi{padding:9px 10px 9px 0}
.ean-phone .ean-kpi:nth-child(2n){padding-left:10px}
.ean-phone .ean-lead p.ean-first::first-letter{font-size:2.6em}
/* ---------- typography: 4 sizes only (headline, article, secondary 14px, labels 11px caps) ---------- */
.ean-kick,.ean-kl,.ean-reg,.ean-chip{font-size:11px;letter-spacing:.06em}
.ean-stamp,.ean-sub,.ean-note,.ean-ks,.ean-mbs,.ean-rm small,.ean-also small,.ean-rl small,.ean-lead p.ean-based{font-size:12.5px}
.ean-bt,.ean-watch,.ean-rl,.ean-also li,.ean-legend,.ean-mbn,.ean-mbv,.ean-tip,.ean-cart small{font-size:14px}
.ean-bk,.ean-rh b,.ean-cart figcaption{font-size:15px}
.ean-foot,.ean-foot p,.ean-meth{font-size:13px;line-height:1.6}
.ean .ean-axis{font-size:11px}
.ean-mbr{padding:5px 0}
/* reading on tablets and phones: larger serif text, generous line spacing (text only) */
.ean-mid .ean-head{font-size:38px;line-height:1.1}
.ean-mid .ean-tone{font-size:20px;line-height:1.45}
.ean-mid .ean-lead p{font-size:20px;line-height:1.62;max-width:none;margin-bottom:18px}
.ean-mid .ean-bt{font-size:15.5px;line-height:1.55}
.ean-mid .ean-bk{font-size:16px}
.ean-mid .ean-watch{font-size:15.5px;line-height:1.55;gap:8px}
.ean-mid .ean-rl{font-size:14.5px;line-height:1.45}
.ean-mid .ean-rh b{font-size:16px}
.ean-mid .ean-ph h3{font-size:20px}
.ean-phone .ean-head{font-size:30px;line-height:1.12;letter-spacing:-.005em}
.ean-phone .ean-tone{font-size:18px;line-height:1.45}
.ean-phone .ean-lead p{font-size:19px;line-height:1.6;max-width:none;margin-bottom:18px}
.ean-phone .ean-briefs li{gap:4px;padding:12px 0}
.ean-phone .ean-bk{font-size:16px}
.ean-phone .ean-bt{font-size:15.5px;line-height:1.55}
.ean-phone .ean-watch{font-size:15.5px;line-height:1.55;gap:10px}
.ean-phone .ean-rh b{font-size:16px}
.ean-phone .ean-rl{font-size:14.5px;line-height:1.45}
.ean-phone .ean-ph h3{font-size:19px}
.ean-phone .ean-cart figcaption{font-size:16px}
.ean-phone .ean-sub{font-size:13px}
.ean-phone .ean-foot{font-size:12.5px}
`

/* ------------------------------------------------------------------ */
/* Texts and page links (all editable in Framer)                        */
/* ------------------------------------------------------------------ */

const DEF_LINKS: Record<string, string> = {
    markets: "/market-data",
    energy: "/energy-terminal",
    crypto: "/crypto-currencies",
    metals: "/hard-assets-terminal",
    estate: "/estate-index",
    corporate: "/corporate-monitor",
    outlook: "/market-outlook",
    islamic: "/islamic-investment",
}

const DEF_TEXTS: Record<string, string> = {
    kicker: "Economic Bearings",
    title: "THE ANALYST",
    subtitle: "Daily Market Analysis & Intelligence. A new edition every morning at 6:30 New York.",
    live: "Today's edition",
    archived: "Archived edition",
    sample: "Sample data",
    unavailable: "Edition unavailable",
    missing: "Today's edition is not available yet. Please check back shortly.",
    nextIn: "Next edition in {t}",
    archive: "Previous editions",
    latest: "Latest edition",
    basedOn: "Based on {d}",
    today: "on the day",
    onDate: "latest data {d}",
    kpi_us_eq: "US stocks (EB US 100)",
    kpi_us10y: "US 10-year yield",
    kpi_brent: "Brent crude",
    kpi_gold: "Gold",
    kpi_eurusd: "EUR/USD",
    kpi_btc: "Bitcoin",
    briefsTitle: "Across our markets",
    briefsNote: "Open a page for the full data",
    barsTitle: "Today's moves",
    barsNote: "Bar = size of the move compared with a usual day",
    contextTitle: "The lead story over one month",
    contextNote: "Change since the first day shown",
    watchTitle: "What we're watching",
    cartoonTitle: "The Weekly Cartoon",
    alsoTitle: "Also in the news",
    alsoNote: "Headlines linked to the themes we follow",
    radarTitle: "Geopolitical radar",
    radarNote: "News volume vs. its recent normal",
    coverage: "{x}× usual coverage",
    st_confirmed: "Moving markets",
    st_news_only: "In the news",
    st_market_only: "Priced, not in the news",
    st_quiet: "Steady",
    page_markets: "Financial Markets",
    page_energy: "Energy Terminal",
    page_crypto: "Crypto & Currencies",
    page_metals: "Hard Assets",
    page_estate: "Estate Index",
    page_corporate: "Corporate Monitor",
    page_outlook: "Market Outlook",
    page_islamic: "Islamic Investment",
    footBold: "For information only, not investment advice.",
    footText:
        "Markets can move for reasons no data set captures. Past moves do not predict future returns.",
    methodTitle: "How THE ANALYST Works",
    methodIntro:
        "THE ANALYST brings together the forces shaping global markets, business and investment.",
    method1Title: "Global Perspective",
    method1:
        "Coverage across financial markets, energy, currencies, digital assets, precious metals, real estate and global business.",
    method2Title: "Market Context",
    method2:
        "Understanding price movements, economic developments and the forces influencing investor sentiment.",
    method3Title: "Connected Insights",
    method3:
        "Exploring the relationships between markets, industries, geopolitics and investment trends.",
    method4Title: "Independent Analysis",
    method4:
        "Clear perspectives, reliable sources and editorial judgement, without losing sight of the bigger picture.",
    methodTagline: "Connecting markets. Understanding what moves them.",
    sourcesTitle: "Sources",
}

const DEFAULTS: Record<string, any> = {
    dataUrl:
        "https://raw.githubusercontent.com/Coorify-1/eb-monitor/main/docs/eb-analyst.json",
    showHeader: true,
    showKpis: true,
    showRadar: true,
    showArchive: true,
    showFooter: true,
    chartHeight: 220,
    maxWidth: 1200,
    padding: 24,
    headlineSize: 42,
    titleSize: 26,
    sectionTitleSize: 18,
    bodySize: 19,
    kpiSize: 22,
    rowSize: 13.5,
    background: "#F0E6DC",
    ink: "#1A1A1A",
    muted: "#7A736C",
    rule: "#D9CFC4",
    strongRule: "#57514B",
    link: "#0D7680",
    upColor: "#1A8F3C",
    downColor: "#D0021B",
    midColor: "#C08A1E",
    links: DEF_LINKS,
    texts: DEF_TEXTS,
}

TheAnalyst.defaultProps = DEFAULTS

const CONTROLS: Record<string, any> = {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        placeholder: "https://raw.githubusercontent.com/…/eb-analyst.json",
        description: "Published every day at 6:30 New York. Empty = sample data.",
    },
    links: {
        type: ControlType.Object,
        title: "Page links",
        description: "Where each link in the text goes. Use your page paths.",
        controls: Object.fromEntries(
            Object.keys(DEF_LINKS).map((k) => [
                k,
                {
                    type: ControlType.String,
                    title: DEF_TEXTS["page_" + k] || k,
                    defaultValue: DEF_LINKS[k],
                },
            ])
        ),
    },
    showHeader: { type: ControlType.Boolean, title: "Header" },
    showKpis: { type: ControlType.Boolean, title: "Key figures" },
    showRadar: { type: ControlType.Boolean, title: "Geopolitical radar" },
    showArchive: { type: ControlType.Boolean, title: "Previous editions" },
    showFooter: { type: ControlType.Boolean, title: "Footer" },
    cartoonImage: {
        type: ControlType.ResponsiveImage,
        title: "Cartoon image",
        description: "The Weekly Cartoon. No image = the block is hidden.",
    },
    cartoonTitle: {
        type: ControlType.String,
        title: "Cartoon title",
        placeholder: "The Weekly Cartoon",
    },
    cartoonCaption: { type: ControlType.String, title: "Cartoon caption", displayTextArea: true },
    cartoonCredit: { type: ControlType.String, title: "Cartoon credit", placeholder: "Drawing: …" },
    cartoonDate: { type: ControlType.String, title: "Cartoon date", placeholder: "Week of Nov 16" },
    cartoonAlt: { type: ControlType.String, title: "Cartoon alt text" },
    chartHeight: {
        type: ControlType.Number,
        title: "Chart height",
        min: 140,
        max: 420,
        step: 10,
        unit: "px",
    },
    maxWidth: {
        type: ControlType.Number,
        title: "Max width",
        min: 320,
        max: 1800,
        step: 10,
        unit: "px",
    },
    padding: { type: ControlType.Number, title: "Padding", min: 0, max: 120, unit: "px" },
    headlineSize: { type: ControlType.Number, title: "Headline size", min: 18, max: 72 },
    titleSize: { type: ControlType.Number, title: "Title size", min: 14, max: 64 },
    sectionTitleSize: { type: ControlType.Number, title: "Section size", min: 12, max: 40 },
    bodySize: { type: ControlType.Number, title: "Article text", min: 13, max: 26, step: 0.5 },
    kpiSize: { type: ControlType.Number, title: "Key figure size", min: 14, max: 48 },
    rowSize: { type: ControlType.Number, title: "Small text", min: 11, max: 20, step: 0.5 },
    headingFont: {
        type: ControlType.Font,
        title: "Heading font",
        controls: "basic",
        defaultFontType: "serif",
    },
    bodyFont: {
        type: ControlType.Font,
        title: "Body font",
        controls: "basic",
        defaultFontType: "sans-serif",
    },
    background: { type: ControlType.Color, title: "Background" },
    ink: { type: ControlType.Color, title: "Text" },
    muted: { type: ControlType.Color, title: "Muted" },
    rule: { type: ControlType.Color, title: "Row lines" },
    strongRule: { type: ControlType.Color, title: "Header lines" },
    link: { type: ControlType.Color, title: "Links / main line" },
    upColor: { type: ControlType.Color, title: "Up" },
    downColor: { type: ControlType.Color, title: "Down" },
    midColor: { type: ControlType.Color, title: "Second line / watch" },
    texts: {
        type: ControlType.Object,
        title: "Texts",
        description: "Edit any label. Leave a field empty to use the default.",
        controls: Object.fromEntries(
            Object.keys(DEF_TEXTS).map((k) => [
                k,
                {
                    type: ControlType.String,
                    title: k
                        .replace(/_/g, " ")
                        .replace(/([A-Z0-9])/g, " $1")
                        .replace(/^./, (c) => c.toUpperCase()),
                    defaultValue: DEF_TEXTS[k],
                    ...(DEF_TEXTS[k].length > 60 ? { displayTextArea: true } : {}),
                },
            ])
        ),
    },
}
Object.keys(CONTROLS).forEach((k) => {
    if (
        CONTROLS[k].defaultValue === undefined &&
        DEFAULTS[k] !== undefined &&
        CONTROLS[k].type !== ControlType.Object
    )
        CONTROLS[k].defaultValue = DEFAULTS[k]
})
addPropertyControls(TheAnalyst, CONTROLS)
