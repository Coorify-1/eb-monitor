import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

/**
 * EB Monitor — Economic Bearings
 * Weekly ranking of 5 banks and 5 companies, "Ranked by the EB Method".
 * Same editorial look as the other EB data components (Crypto & FX, Metals, Markets):
 * flat beige page, serif titles and numbers, sans-serif text, thin rules,
 * ▲ green / ▼ red, blue text tabs.
 *
 * Banking on top, Company below. Each section: Carousel, Row, Spotlight or Ranking.
 * Click a card to open the full analysis (CEO profile, key metrics, EB Score, risks).
 *
 * Data: one JSON file published weekly (Monday 7:00 am New York) by the EB engine.
 * Leave "Data URL" empty to see the built-in SAMPLE data (fictional companies).
 * No cookies, no third-party scripts, no API key.
 *
 * @framerIntrinsicWidth 1200
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight auto
 */

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type Pillar = { key: string; label: string; score: number; weight?: number }
type Metric = {
    label: string
    sub?: string
    value: string
    change?: number | null
    unit?: "%" | "pt"
    good?: "up" | "down"
    note?: string
}
type CEO = {
    name: string
    title?: string
    since?: string | number
    bio?: string
    photo?: string
    photoCredit?: string
}
type Item = {
    rank: number
    prevRank?: number | null
    name: string
    ticker: string
    exchange?: string
    country: string
    city?: string
    sector?: string
    score: number
    pillars: Pillar[]
    why?: string
    headline?: { label: string; value: string; period?: string }
    employees?: number
    website?: string
    logo?: string
    ceo?: CEO
    team?: { role: string; name: string }[]
    metrics?: Metric[]
    risks?: string[]
}
type Feed = {
    sample?: boolean
    week?: string
    asOf?: string
    nextUpdate?: string
    regime?: { label: string; score?: number; note?: string }
    banking?: Item[]
    company?: Item[]
    sources?: string
}
type Kind = "banking" | "company"
type Layout = "carousel" | "row" | "spotlight" | "ranking"

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const isNum = (v: any): v is number => typeof v === "number" && isFinite(v)

const fam = (f: any, fallback: string) =>
    f && f.fontFamily
        ? '"' + String(f.fontFamily).replace(/"/g, "") + '",' + fallback
        : ""

let regionNames: any = null
const countryName = (cc: string) => {
    if (!cc) return ""
    try {
        if (
            !regionNames &&
            typeof Intl !== "undefined" &&
            (Intl as any).DisplayNames
        )
            regionNames = new (Intl as any).DisplayNames(["en"], {
                type: "region",
            })
        return (regionNames && regionNames.of(cc.toUpperCase())) || cc
    } catch {
        return cc
    }
}

const STOP = ["the", "of", "and", "de", "la", "le", "du"]
const initials = (name: string) => {
    const words = String(name || "")
        .replace(/[^\p{L}\p{N}\s]/gu, " ")
        .split(/\s+/)
        .filter(Boolean)
    const main = words.filter((w) => !STOP.includes(w.toLowerCase()))
    const use = (main.length ? main : words).slice(0, 2)
    return use.map((w) => w[0].toUpperCase()).join("") || "?"
}

const host = (url?: string) => {
    if (!url) return ""
    return url.replace(/^https?:\/\//, "").replace(/\/$/, "")
}
const href = (url?: string) =>
    !url ? "" : /^https?:\/\//.test(url) ? url : "https://" + url

const fmtInt = (n?: number) => (isNum(n) ? n.toLocaleString("en-US") : "")

/* ---------- New York clock ---------- */

const NY = "America/New_York"
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

function nyParts(d: Date): Record<string, string> {
    const o: Record<string, string> = {}
    try {
        new Intl.DateTimeFormat("en-US", {
            timeZone: NY,
            hourCycle: "h23",
            weekday: "short",
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        })
            .formatToParts(d)
            .forEach((p) => (o[p.type] = p.value))
    } catch {}
    return o
}
// New York offset from UTC at an instant, in ms (e.g. -5 h)
function nyOffset(d: Date) {
    const p = nyParts(d)
    const wall = Date.UTC(
        +p.year,
        +p.month - 1,
        +p.day,
        +p.hour % 24,
        +p.minute,
        +p.second
    )
    return wall - Math.floor(d.getTime() / 1000) * 1000
}
// Next given weekday + time, New York wall clock (1 = Monday)
function nextNY(weekday: number, hour: number, minute: number, now: Date) {
    const p = nyParts(now)
    const wd = DAYS.indexOf(p.weekday)
    if (wd < 0) return null
    let add = (weekday - wd + 7) % 7
    const cur = (+p.hour % 24) * 60 + +p.minute
    if (add === 0 && cur >= hour * 60 + minute) add = 7
    const wall = Date.UTC(+p.year, +p.month - 1, +p.day + add, hour, minute, 0)
    let t = wall - nyOffset(new Date(wall))
    t = wall - nyOffset(new Date(t))
    return new Date(t)
}
const nyTime = (d: Date) => {
    try {
        return d.toLocaleTimeString("en-US", {
            timeZone: NY,
            hour: "numeric",
            minute: "2-digit",
        })
    } catch {
        return ""
    }
}
const nyDay = (d: Date) => {
    try {
        return d.toLocaleDateString("en-US", {
            timeZone: NY,
            weekday: "short",
            month: "short",
            day: "numeric",
        })
    } catch {
        return ""
    }
}
const countdown = (ms: number) => {
    if (ms <= 0) return ""
    const m = Math.floor(ms / 60000)
    const d = Math.floor(m / 1440)
    const h = Math.floor((m % 1440) / 60)
    const mm = m % 60
    return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${mm}m` : `${mm}m`
}

function useNow(enabled: boolean, every = 30000) {
    const [now, setNow] = React.useState<Date>(() => new Date())
    React.useEffect(() => {
        if (!enabled) return
        setNow(new Date())
        const id = setInterval(() => setNow(new Date()), every)
        return () => clearInterval(id)
    }, [enabled, every])
    return now
}

/* ---------- Data ---------- */

function useFeed(url: string) {
    const [feed, setFeed] = React.useState<Feed | null>(url ? null : SAMPLE)
    const [state, setState] = React.useState<
        "sample" | "loading" | "ok" | "error"
    >(url ? "loading" : "sample")
    React.useEffect(() => {
        if (!url) {
            setFeed(SAMPLE)
            setState("sample")
            return
        }
        let dead = false
        let have = false
        const KEY = "ebm_feed_v1|" + url
        try {
            const c = JSON.parse(window.localStorage.getItem(KEY) || "null")
            if (c && c.feed) {
                setFeed(c.feed)
                setState("ok")
                have = true
            }
        } catch {}
        const load = () =>
            fetch(url, { cache: "no-cache" })
                .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
                .then((j: Feed) => {
                    if (dead) return
                    if (
                        !j ||
                        (!Array.isArray(j.banking) && !Array.isArray(j.company))
                    )
                        throw new Error("bad data")
                    setFeed(j)
                    setState("ok")
                    have = true
                    try {
                        window.localStorage.setItem(
                            KEY,
                            JSON.stringify({ at: Date.now(), feed: j })
                        )
                    } catch {}
                })
                .catch(() => {
                    if (!dead && !have) setState("error")
                })
        if (!have) setState("loading")
        load()
        const id = setInterval(load, 30 * 60 * 1000)
        return () => {
            dead = true
            clearInterval(id)
        }
    }, [url])
    return { feed, state }
}

/* ------------------------------------------------------------------ */
/* Small parts                                                         */
/* ------------------------------------------------------------------ */

function Flag({ cc, size = 14 }: { cc: string; size?: number }) {
    if (!size || !cc) return null
    const svg = FLAG_SVG[cc.toUpperCase()]
    return (
        <span
            className="ebm-flag"
            style={{ width: size, height: size }}
            aria-hidden
        >
            {svg ? (
                <img
                    src={
                        "data:image/svg+xml;charset=utf-8," +
                        encodeURIComponent(svg)
                    }
                    alt=""
                    width={size}
                    height={size}
                />
            ) : (
                <span
                    className="ebm-flag-txt"
                    style={{ fontSize: Math.max(7, size * 0.42) }}
                >
                    {cc.toUpperCase().slice(0, 2)}
                </span>
            )}
        </span>
    )
}

function Mark({
    name,
    src,
    size,
    round = true,
    logo = false,
}: {
    name: string
    src?: string
    size: number
    round?: boolean
    logo?: boolean
}) {
    const [bad, setBad] = React.useState(false)
    React.useEffect(() => setBad(false), [src])
    const style = { width: size, height: size, borderRadius: 0 } // square photos and logos
    if (src && !bad)
        return (
            <span
                className={"ebm-mark is-img" + (logo ? " is-logo" : "")}
                style={style}
            >
                <img
                    src={src}
                    alt=""
                    loading="lazy"
                    onError={() => setBad(true)}
                />
            </span>
        )
    return (
        <span
            className="ebm-mark"
            style={{ ...style, fontSize: Math.max(10, size * 0.38) }}
            aria-hidden
        >
            {initials(name)}
        </span>
    )
}

function Move({ it, tx }: { it: Item; tx: Record<string, string> }) {
    if (it.prevRank === undefined) return null
    if (it.prevRank === null)
        return <span className="ebm-move up">{tx.moveNew}</span>
    if (it.prevRank === it.rank)
        return <span className="ebm-move flat">{tx.moveHeld}</span>
    const up = it.prevRank > it.rank
    return (
        <span className={"ebm-move " + (up ? "up" : "dn")}>
            {up ? "▲" : "▼"} {tx.moveFrom.replace("{n}", String(it.prevRank))}
        </span>
    )
}

// Hairline meter: thin rule, ink line up to the score, small dot at the score.
// "mid" draws a tick at 50 = sector median.
function Meter({
    v,
    size = "sm",
    mid,
}: {
    v: number
    size?: "sm" | "lg"
    mid?: boolean
}) {
    const x = Math.max(0, Math.min(100, Number(v) || 0))
    return (
        <span className={"ebm-meter is-" + size} aria-hidden>
            {mid && <s />}
            <i style={{ width: x + "%" }} />
            <b style={{ left: x + "%" }} />
        </span>
    )
}

function Bar({ p }: { p: Pillar }) {
    const v = Math.max(0, Math.min(100, Number(p.score) || 0))
    return (
        <div className="ebm-bar">
            <span className="ebm-barlab">{p.label}</span>
            <Meter v={v} />
            <span className="num">{Math.round(v)}</span>
        </div>
    )
}

function Tabs({
    items,
    value,
    onPick,
    label,
}: {
    items: { v: string; t: string }[]
    value: string
    onPick: (v: any) => void
    label: string
}) {
    return (
        <div className="ebm-tabs" role="group" aria-label={label}>
            {items.map((it, i) => (
                <React.Fragment key={it.v}>
                    {i > 0 && <span className="ebm-sep">|</span>}
                    <button
                        type="button"
                        aria-pressed={value === it.v}
                        onClick={() => onPick(it.v)}
                    >
                        {it.t}
                    </button>
                </React.Fragment>
            ))}
        </div>
    )
}

function Chevron({ dir }: { dir: "left" | "right" | "down" | "up" }) {
    const d =
        dir === "left"
            ? "M6.5 1.5 L3 5 L6.5 8.5"
            : dir === "right"
              ? "M3.5 1.5 L7 5 L3.5 8.5"
              : dir === "up"
                ? "M1.5 6.5 L5 3 L8.5 6.5"
                : "M1.5 3.5 L5 7 L8.5 3.5"
    return (
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
            <path
                d={d}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    )
}

const pickable = (on: () => void, pressed: boolean) => ({
    onClick: on,
    onKeyDown: (e: React.KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            on()
        }
    },
    tabIndex: 0,
    role: "button",
    "aria-expanded": pressed,
})

/* ------------------------------------------------------------------ */
/* Card, row, carousel                                                 */
/* ------------------------------------------------------------------ */

function Card({
    it,
    sel,
    onPick,
    bars,
    showWhy,
    big,
    logoSize,
    tx,
}: {
    it: Item
    sel: boolean
    onPick: () => void
    bars: number
    showWhy: boolean
    big?: boolean
    logoSize: number
    tx: Record<string, string>
}) {
    const ps = (it.pillars || []).slice(0, big ? 99 : bars)
    return (
        <article
            className={
                "ebm-card is-click" +
                (sel ? " is-sel" : "") +
                (big ? " is-big" : "")
            }
            {...pickable(onPick, sel)}
            aria-label={`${it.rank}. ${it.name}, EB Score ${it.score}`}
        >
            <div className="ebm-ctop">
                <span className="ebm-rank">{it.rank}</span>
                <Move it={it} tx={tx} />
            </div>
            <div className="ebm-id">
                <Mark
                    name={it.name}
                    src={it.logo}
                    size={big ? logoSize + 8 : logoSize}
                    logo
                />
                <div className="ebm-idtxt">
                    <div className="ebm-name">{it.name}</div>
                    <div className="ebm-sub">
                        <Flag cc={it.country} size={12} />
                        <span>
                            {it.ticker}
                            {it.country ? " · " + countryName(it.country) : ""}
                        </span>
                    </div>
                </div>
            </div>
            <div className="ebm-scorerow">
                <span className="ebm-lab">{tx.score}</span>
                <span className="ebm-score">
                    {Math.round(it.score)}
                    <small> /100</small>
                </span>
            </div>
            {ps.length > 0 && (
                <div className="ebm-bars">
                    {ps.map((p) => (
                        <Bar key={p.key} p={p} />
                    ))}
                </div>
            )}
            {showWhy && it.why && <p className="ebm-why">{it.why}</p>}
            <span className="ebm-open">
                {sel ? tx.close : tx.open}
                <Chevron dir={sel ? "up" : "down"} />
            </span>
        </article>
    )
}

function Track({
    items,
    visible,
    arrows,
    render,
    tx,
    toolbar,
}: {
    items: Item[]
    visible: number
    arrows: boolean
    render: (it: Item) => React.ReactNode
    tx: Record<string, string>
    toolbar?: React.ReactNode
}) {
    const ref = React.useRef<HTMLDivElement>(null)
    const [pos, setPos] = React.useState({
        first: 1,
        last: Math.min(visible, items.length),
    })
    const update = React.useCallback(() => {
        const el = ref.current
        if (!el) return
        const kids = Array.from(el.children) as HTMLElement[]
        const L = el.scrollLeft
        const R = L + el.clientWidth
        let first = 0
        let last = 0
        kids.forEach((c, i) => {
            const a = c.offsetLeft
            const b = a + c.offsetWidth
            if (a >= L - 4 && b <= R + 4) {
                if (!first) first = i + 1
                last = i + 1
            }
        })
        if (!first) {
            first = 1
            last = 1
        }
        setPos((p) =>
            p.first === first && p.last === last ? p : { first, last }
        )
    }, [])
    React.useEffect(() => {
        update()
        const el = ref.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver(update)
        ro.observe(el)
        return () => ro.disconnect()
    }, [items.length, update])
    const go = (dir: number) => {
        const el = ref.current
        if (!el) return
        const kids = Array.from(el.children) as HTMLElement[]
        const step =
            kids.length > 1
                ? kids[1].offsetLeft - kids[0].offsetLeft
                : el.clientWidth
        let reduce = false
        try {
            reduce = window.matchMedia(
                "(prefers-reduced-motion: reduce)"
            ).matches
        } catch {}
        el.scrollBy({ left: dir * step, behavior: reduce ? "auto" : "smooth" })
    }
    const all = pos.first <= 1 && pos.last >= items.length
    return (
        <div className="ebm-carousel">
            <div className="ebm-toolbar">
                {toolbar || <span />}
                {arrows && !all && (
                    <div className="ebm-nav">
                        <span className="ebm-count">
                            {tx.showing
                                .replace("{a}", String(pos.first))
                                .replace("{b}", String(pos.last))
                                .replace("{n}", String(items.length))}
                        </span>
                        <button
                            type="button"
                            className="ebm-arrow"
                            aria-label={tx.prev}
                            data-off={pos.first <= 1 || undefined}
                            onClick={() => go(-1)}
                        >
                            <Chevron dir="left" />
                        </button>
                        <button
                            type="button"
                            className="ebm-arrow"
                            aria-label={tx.next}
                            data-off={pos.last >= items.length || undefined}
                            onClick={() => go(1)}
                        >
                            <Chevron dir="right" />
                        </button>
                    </div>
                )}
            </div>
            <div
                className="ebm-track"
                ref={ref}
                onScroll={update}
                style={{ ["--vis" as any]: visible }}
            >
                {items.map((it) => (
                    <div className="ebm-slot" key={it.ticker + it.rank}>
                        {render(it)}
                    </div>
                ))}
            </div>
        </div>
    )
}

function RankTable({
    items,
    selKey,
    onPick,
    tx,
    logoSize,
    compact,
}: {
    items: Item[]
    selKey: string | null
    onPick: (it: Item) => void
    tx: Record<string, string>
    logoSize: number
    compact?: boolean
}) {
    const heads = (items[0]?.pillars || []).slice(0, 4)
    return (
        <table className={"ebm-tbl" + (compact ? " is-compact" : "")}>
            <thead>
                <tr>
                    <th className="c-rank">#</th>
                    <th>{tx.name}</th>
                    <th className="c-score">{tx.score}</th>
                    {!compact &&
                        heads.map((h) => (
                            <th key={h.key} className="r c-pil">
                                {h.label}
                            </th>
                        ))}
                    <th className="r c-move">{tx.week}</th>
                </tr>
            </thead>
            <tbody>
                {items.map((it) => {
                    const k = it.ticker + it.rank
                    const sel = selKey === k
                    return (
                        <tr
                            key={k}
                            className={"is-click" + (sel ? " is-sel" : "")}
                            {...pickable(() => onPick(it), sel)}
                        >
                            <td className="c-rank num">{it.rank}</td>
                            <td>
                                <span className="ebm-tname">
                                    <Mark
                                        name={it.name}
                                        src={it.logo}
                                        size={Math.round(logoSize * 0.7)}
                                        logo
                                    />
                                    <span>
                                        <span className="ebm-tn">
                                            {it.name}
                                        </span>
                                        <span className="ebm-sub">
                                            <Flag cc={it.country} size={11} />
                                            {it.ticker}
                                        </span>
                                    </span>
                                </span>
                            </td>
                            <td className="c-score">
                                <span className="ebm-tscore">
                                    <span className="num">
                                        {Math.round(it.score)}
                                    </span>
                                    <Meter v={it.score} />
                                </span>
                            </td>
                            {!compact &&
                                heads.map((h) => {
                                    const p = (it.pillars || []).find(
                                        (x) => x.key === h.key
                                    )
                                    return (
                                        <td key={h.key} className="r num c-pil">
                                            {p ? Math.round(p.score) : "—"}
                                        </td>
                                    )
                                })}
                            <td className="r c-move">
                                <Move it={it} tx={tx} />
                            </td>
                        </tr>
                    )
                })}
            </tbody>
        </table>
    )
}

/* ------------------------------------------------------------------ */
/* Detail panel (full analysis)                                        */
/* ------------------------------------------------------------------ */

function Change({ m }: { m: Metric }) {
    if (!isNum(m.change)) return null
    const s = Math.sign(m.change)
    const goodUp = m.good !== "down"
    const tone = s === 0 ? "flat" : s > 0 === goodUp ? "up" : "dn"
    const v = Math.abs(m.change)
    const txt = m.unit === "pt" ? `${v.toFixed(1)} pt` : `${v.toFixed(1)}%`
    return (
        <span className={"ebm-chg " + tone}>
            {s > 0 ? "▲" : s < 0 ? "▼" : "—"} {txt}
        </span>
    )
}

function Detail({
    it,
    kind,
    onClose,
    tx,
    p,
}: {
    it: Item
    kind: Kind
    onClose: () => void
    tx: Record<string, string>
    p: any
}) {
    const [tab, setTab] = React.useState("overview")
    React.useEffect(() => setTab("overview"), [it.ticker])
    const ref = React.useRef<HTMLDivElement>(null)
    React.useEffect(() => {
        const el = ref.current
        if (!el || p.scrollToDetail === false) return
        const r = el.getBoundingClientRect()
        const vh = window.innerHeight || 800
        if (r.top < 0 || r.top > vh * 0.75) {
            try {
                el.scrollIntoView({ behavior: "smooth", block: "nearest" })
            } catch {}
        }
    }, [it.ticker])
    const metrics = it.metrics || []
    const where = [it.city, countryName(it.country)].filter(Boolean).join(", ")
    const sectionName = kind === "banking" ? tx.bankingTitle : tx.companyTitle
    const TABS = [
        { v: "overview", t: tx.tOverview },
        { v: "score", t: tx.tScore },
        { v: "financials", t: tx.tFinancials },
        ...(it.risks && it.risks.length ? [{ v: "risks", t: tx.tRisks }] : []),
    ]
    const ceo = it.ceo
    return (
        <div className="ebm-detail" ref={ref} aria-live="polite">
            <div className="ebm-dhead">
                <div className="ebm-dhl">
                    <Mark name={it.name} src={it.logo} size={44} logo />
                    <div>
                        <h4 className="ebm-dname">{it.name}</h4>
                        <div className="ebm-caps">
                            {[
                                where,
                                it.exchange
                                    ? it.exchange + ": " + it.ticker
                                    : it.ticker,
                                `#${it.rank} ${sectionName}`,
                            ]
                                .filter(Boolean)
                                .join(" · ")}
                        </div>
                    </div>
                </div>
                {it.headline && (
                    <div className="ebm-dhr">
                        <div className="ebm-hval">{it.headline.value}</div>
                        <div className="ebm-caps">
                            {it.headline.label}
                            {it.headline.period
                                ? ` (${it.headline.period})`
                                : ""}
                        </div>
                    </div>
                )}
            </div>
            {(isNum(it.employees) || it.website || it.sector) && (
                <div className="ebm-dmeta">
                    <span className="ebm-dmeta-l">
                        {it.sector && <span>{it.sector}</span>}
                        {isNum(it.employees) && (
                            <span>
                                {fmtInt(it.employees)} {tx.employees}
                            </span>
                        )}
                    </span>
                    {it.website && (
                        <a
                            className="ebm-link"
                            href={href(it.website)}
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            {host(it.website)} ↗
                        </a>
                    )}
                </div>
            )}
            <div className="ebm-dtabs">
                <Tabs
                    label={tx.analysis}
                    value={tab}
                    onPick={setTab}
                    items={TABS}
                />
                <button
                    type="button"
                    className="ebm-x"
                    onClick={onClose}
                    aria-label={tx.close}
                >
                    ×
                </button>
            </div>

            {tab === "overview" && (
                <div className="ebm-dgrid">
                    <div className="ebm-dleft">
                        <div className="ebm-caps">{tx.leadership}</div>
                        {ceo ? (
                            <>
                                <div className="ebm-ceo">
                                    <Mark
                                        name={ceo.name}
                                        src={ceo.photo}
                                        size={56}
                                    />
                                    <div>
                                        <div className="ebm-ceoname">
                                            {ceo.name}
                                        </div>
                                        <div className="ebm-sub">
                                            {ceo.title || tx.ceo}
                                            {ceo.since
                                                ? " · " +
                                                  tx.since +
                                                  " " +
                                                  ceo.since
                                                : ""}
                                        </div>
                                    </div>
                                </div>
                                {ceo.photo && ceo.photoCredit && (
                                    <div className="ebm-credit">
                                        {tx.photo} {ceo.photoCredit}
                                    </div>
                                )}
                                {ceo.bio && (
                                    <p className="ebm-bio">{ceo.bio}</p>
                                )}
                            </>
                        ) : (
                            <p className="ebm-bio">{tx.noCeo}</p>
                        )}
                        {it.team && it.team.length > 0 && (
                            <table className="ebm-mini">
                                <tbody>
                                    {it.team.map((t) => (
                                        <tr key={t.role}>
                                            <td>{t.role}</td>
                                            <td className="r">{t.name}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                        {it.why && (
                            <div className="ebm-whybox">
                                <div className="ebm-caps">{tx.whyTitle}</div>
                                <p>{it.why}</p>
                            </div>
                        )}
                    </div>
                    <div className="ebm-dright">
                        <div className="ebm-row">
                            <span className="ebm-caps">{tx.keyMetrics}</span>
                            <span className="ebm-meta">{tx.vsPrior}</span>
                        </div>
                        <div className="ebm-metrics">
                            {metrics.slice(0, 4).map((m) => (
                                <div className="ebm-m" key={m.label}>
                                    <span>
                                        <span className="ebm-mlab">
                                            {m.label}
                                        </span>
                                        {m.sub && (
                                            <span className="ebm-msub">
                                                {m.sub}
                                            </span>
                                        )}
                                    </span>
                                    <span className="ebm-mval">
                                        <span className="ebm-mnum">
                                            {m.value}
                                        </span>
                                        <Change m={m} />
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {tab === "score" && (
                <div className="ebm-dgrid">
                    <div className="ebm-dleft">
                        <div className="ebm-caps">{tx.score}</div>
                        <div className="ebm-bigscore">
                            {Math.round(it.score)}
                            <small> /100</small>
                        </div>
                        <p className="ebm-bio">{tx.scoreHint}</p>
                    </div>
                    <div className="ebm-dright">
                        <div className="ebm-row">
                            <span className="ebm-caps">{tx.pillars}</span>
                            <span className="ebm-meta">{tx.weight}</span>
                        </div>
                        <div className="ebm-pillars">
                            {(it.pillars || []).map((pl) => (
                                <div className="ebm-pil" key={pl.key}>
                                    <div className="ebm-pilhead">
                                        <span>{pl.label}</span>
                                        <span className="ebm-meta">
                                            {isNum(pl.weight)
                                                ? pl.weight + "%"
                                                : ""}
                                        </span>
                                    </div>
                                    <div className="ebm-pilbar">
                                        <Meter v={pl.score} size="lg" mid />
                                        <span className="num">
                                            {Math.round(pl.score)}
                                        </span>
                                    </div>
                                    {PILLAR_INFO[kind][pl.key] && (
                                        <div className="ebm-msub">
                                            {PILLAR_INFO[kind][pl.key]}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {tab === "financials" && (
                <div className="ebm-fin">
                    <table className="ebm-tbl ebm-fintbl">
                        <thead>
                            <tr>
                                <th>{tx.metric}</th>
                                <th className="r">{tx.value}</th>
                                <th className="r">{tx.change}</th>
                                <th className="c-note">{tx.meaning}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {metrics.map((m) => (
                                <tr key={m.label}>
                                    <td>{m.label}</td>
                                    <td className="r num">{m.value}</td>
                                    <td className="r">
                                        <Change m={m} />
                                    </td>
                                    <td className="c-note">
                                        {m.note || GLOSSARY[m.label] || ""}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {tab === "risks" && it.risks && (
                <ul className="ebm-risks">
                    {it.risks.map((r, i) => (
                        <li key={i}>{r}</li>
                    ))}
                </ul>
            )}
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Section                                                             */
/* ------------------------------------------------------------------ */

function Section({
    kind,
    items,
    layout,
    p,
    tx,
    week,
    hideTitle,
}: {
    kind: Kind
    items: Item[]
    layout: Layout
    p: any
    tx: Record<string, string>
    week?: string
    hideTitle?: boolean
}) {
    const [view, setView] = React.useState<Layout>(layout)
    React.useEffect(() => setView(layout), [layout])
    const [selKey, setSelKey] = React.useState<string | null>(null)
    const sorted = [...items].sort((a, b) => a.rank - b.rank)
    const sel = sorted.find((it) => it.ticker + it.rank === selKey) || null
    const toggle = (it: Item) => {
        const k = it.ticker + it.rank
        setSelKey((s) => (s === k ? null : k))
    }
    const bars = Math.max(0, Math.min(5, Number(p.cardBars) || 0))
    const showWhy = p.showWhy !== false
    const logo = Math.max(24, Math.min(64, Number(p.logoSize) || 36))
    const vis = Math.max(1, Math.min(5, Number(p.cardsVisible) || 3))
    const card = (it: Item, big?: boolean) => (
        <Card
            it={it}
            sel={selKey === it.ticker + it.rank}
            onPick={() => toggle(it)}
            bars={bars}
            showWhy={showWhy}
            big={big}
            logoSize={logo}
            tx={tx}
        />
    )
    const title = kind === "banking" ? tx.bankingTitle : tx.companyTitle
    const note = kind === "banking" ? tx.bankingNote : tx.companyNote
    const switchItems = [
        { v: layout === "ranking" ? "carousel" : layout, t: tx.viewCards },
        { v: "ranking", t: tx.viewRanking },
    ]

    const toolbar =
        p.readerSwitch !== false && sorted.length > 0 ? (
            <Tabs
                label={tx.view}
                value={view === "ranking" ? "ranking" : switchItems[0].v}
                onPick={(v) => setView(v)}
                items={switchItems}
            />
        ) : null
    const plain = toolbar ? <div className="ebm-toolbar">{toolbar}</div> : null

    let body: React.ReactNode = null
    if (!sorted.length) body = <p className="ebm-note">{tx.empty}</p>
    else if (view === "ranking")
        body = (
            <>
                {plain}
                <RankTable
                    items={sorted}
                    selKey={selKey}
                    onPick={toggle}
                    tx={tx}
                    logoSize={logo}
                />
            </>
        )
    else if (view === "spotlight")
        body = (
            <>
                {plain}
                <div className="ebm-spot">
                    <div className="ebm-spot-l">{card(sorted[0], true)}</div>
                    <div className="ebm-spot-r">
                        <RankTable
                            items={sorted.slice(1)}
                            selKey={selKey}
                            onPick={toggle}
                            tx={tx}
                            logoSize={logo}
                            compact
                        />
                    </div>
                </div>
            </>
        )
    else
        body = (
            <Track
                items={sorted}
                visible={view === "row" ? sorted.length : vis}
                arrows={view === "carousel"}
                render={(it) => card(it)}
                tx={tx}
                toolbar={toolbar}
            />
        )

    return (
        <section
            className={"ebm-sec" + (hideTitle ? " is-switched" : "")}
            id={kind === "banking" ? "banking-monitor" : "company-monitor"}
            role={hideTitle ? "tabpanel" : undefined}
        >
            <div className="ebm-row ebm-sechead">
                {hideTitle ? <span /> : <h3 className="ebm-h">{title}</h3>}
                <span className="ebm-meta">
                    {note}
                    {week ? " · " + tx.weekLabel + " " + week : ""}
                </span>
            </div>
            {body}
            {sel && (
                <Detail
                    it={sel}
                    kind={kind}
                    onClose={() => setSelKey(null)}
                    tx={tx}
                    p={p}
                />
            )}
        </section>
    )
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export default function EBMonitor(props: any) {
    const clean = (o: any) =>
        Object.fromEntries(
            Object.entries(o || {}).filter(
                ([, v]) => v !== undefined && v !== null && v !== ""
            )
        )
    const p: any = { ...DEFAULTS, ...clean(props) }
    const keepEmpty = (o: any) =>
        Object.fromEntries(
            Object.entries(o || {}).filter(
                ([, v]) => v !== undefined && v !== null
            )
        )
    const tx = { ...DEF_TEXTS, ...keepEmpty(p.texts) } as Record<string, string>
    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    const url = String(p.dataUrl || "").trim()
    const { feed, state } = useFeed(url)
    const data: Feed | null = feed || (isCanvas ? SAMPLE : null)
    const isSample = !url || !!(data && data.sample)

    const now = useNow(!!p.showHeader && p.showClock !== false)
    // Use the feed's date only if it is still in the future; otherwise
    // (stale feed, past date, bad value) compute next Monday 7:00 New York.
    const feedNext =
        data && data.nextUpdate ? new Date(data.nextUpdate) : null
    const next =
        feedNext &&
        isFinite(feedNext.getTime()) &&
        feedNext.getTime() > now.getTime()
            ? feedNext
            : nextNY(1, 7, 0, now)
    const nextOk = next && isFinite(next.getTime())

    const vars = {
        "--bg": p.background,
        "--ink": p.ink,
        "--mute": p.muted,
        "--rule": p.rule,
        "--strong": p.strongRule,
        "--link": p.link,
        "--up": p.upColor,
        "--dn": p.downColor,
        "--maxw": Math.max(320, Number(p.maxWidth) || 1040) + "px",
        "--padx": Math.max(0, Number(p.padding) || 0) + "px",
        "--padt": Math.max(0, Number(p.spaceTop) || 0) + "px",
        "--padb": Math.max(0, Number(p.spaceBottom) || 0) + "px",
        "--secgap": Math.max(0, Number(p.sectionGap) || 0) + "px",
        "--gap": Math.max(8, Number(p.cardGap) || 24) + "px",
        "--t1": Math.max(14, Number(p.titleSize) || 22) + "px",
        "--t2": Math.max(12, Number(p.sectionTitleSize) || 18) + "px",
        "--row": Math.max(11, Number(p.rowSize) || 15) + "px",
        "--big": Math.max(16, Number(p.scoreSize) || 28) + "px",
        "--fsz": Math.max(9, Math.min(18, Number(p.footerSize) || 11)) + "px",
        "--fh":
            fam(p.headingFont, 'Georgia,"Times New Roman",serif') ||
            '"Libre Caslon Text",Georgia,"Times New Roman",serif',
        "--fb":
            fam(p.bodyFont, '"Helvetica Neue",Arial,sans-serif') ||
            'Inter,"Helvetica Neue",Arial,sans-serif',
    } as React.CSSProperties

    const [open, setOpen] = React.useState(false)
    const regime = data && data.regime
    const regTone = regime
        ? /on/i.test(regime.label)
            ? "up"
            : /off/i.test(regime.label)
              ? "dn"
              : "flat"
        : "flat"

    const sections = [
        p.showBanking && data
            ? {
                  kind: "banking" as Kind,
                  items: data.banking || [],
                  layout: p.bankingLayout,
              }
            : null,
        p.showCompany && data
            ? {
                  kind: "company" as Kind,
                  items: data.company || [],
                  layout: p.companyLayout,
              }
            : null,
    ].filter(Boolean) as { kind: Kind; items: Item[]; layout: Layout }[]

    // One monitor at a time: Banking | Company switch
    const both = sections.length > 1
    const [active, setActive] = React.useState<Kind>(
        p.startWith === "company" ? "company" : "banking"
    )
    React.useEffect(() => {
        setActive(p.startWith === "company" ? "company" : "banking")
    }, [p.startWith])
    React.useEffect(() => {
        // a link to …#company-monitor or …#banking-monitor opens that monitor
        try {
            const h = window.location.hash
            if (/company/i.test(h)) setActive("company")
            else if (/bank/i.test(h)) setActive("banking")
        } catch {}
    }, [])
    const shown = both ? sections.filter((s) => s.kind === active) : sections

    return (
        <div className="ebm" style={vars}>
            <style>{CSS}</style>
            <div className="ebm-wrap">
                {p.showHeader && (
                    <header className="ebm-head">
                        <div className="ebm-row">
                            <h2 className="ebm-title">{tx.title}</h2>
                            {p.showClock !== false && (
                                <span className="ebm-meta ebm-clock">
                                    <span
                                        className={
                                            "ebm-dot" +
                                            (state === "error"
                                                ? ""
                                                : " is-live")
                                        }
                                    />
                                    {tx.newYork} {nyTime(now)}
                                    {nextOk && (
                                        <>
                                            {" · "}
                                            {tx.nextUpdate} {nyDay(next!)},{" "}
                                            {nyTime(next!)}
                                            {countdown(
                                                next!.getTime() - now.getTime()
                                            )
                                                ? " · " +
                                                  tx.inTime.replace(
                                                      "{t}",
                                                      countdown(
                                                          next!.getTime() -
                                                              now.getTime()
                                                      )
                                                  )
                                                : ""}
                                        </>
                                    )}
                                </span>
                            )}
                        </div>
                        {tx.subtitle && (
                            <p className="ebm-subt">{tx.subtitle}</p>
                        )}
                        {(p.showRegime !== false && regime) || isSample ? (
                            <div className="ebm-strip">
                                {p.showRegime !== false && regime && (
                                    <span>
                                        <span className="ebm-lab">
                                            {tx.regime}
                                        </span>{" "}
                                        <b className={regTone}>
                                            {regime.label}
                                        </b>
                                        {isNum(regime.score) && (
                                            <span className="ebm-meta">
                                                {" "}
                                                {Math.round(regime.score)}/100
                                            </span>
                                        )}
                                        {regime.note && (
                                            <span className="ebm-meta">
                                                {" "}
                                                · {regime.note}
                                            </span>
                                        )}
                                    </span>
                                )}
                                {isSample && (
                                    <span className="ebm-sample">
                                        {tx.sampleBadge}
                                    </span>
                                )}
                            </div>
                        ) : null}
                    </header>
                )}

                {state === "loading" && !data && (
                    <p className="ebm-note">{tx.loading}</p>
                )}
                {state === "error" && !feed && !isCanvas && (
                    <p className="ebm-note is-err">{tx.unavailable}</p>
                )}

                {both && (
                    <nav
                        className="ebm-monitors"
                        role="tablist"
                        aria-label={tx.monitors}
                    >
                        {sections.map((s) => {
                            const on = s.kind === active
                            return (
                                <button
                                    key={s.kind}
                                    type="button"
                                    role="tab"
                                    aria-selected={on}
                                    aria-controls={
                                        s.kind === "banking"
                                            ? "banking-monitor"
                                            : "company-monitor"
                                    }
                                    className={"ebm-mon" + (on ? " is-on" : "")}
                                    onClick={() => setActive(s.kind)}
                                >
                                    {s.kind === "banking"
                                        ? tx.bankingTitle
                                        : tx.companyTitle}
                                </button>
                            )
                        })}
                    </nav>
                )}

                {shown.map((s) => (
                    <Section
                        key={s.kind}
                        kind={s.kind}
                        items={s.items}
                        layout={s.layout}
                        p={p}
                        tx={tx}
                        week={data?.week}
                        hideTitle={both}
                    />
                ))}

                {p.showFooter && (
                    <footer className="ebm-foot">
                        <div className="ebm-refresh">
                            <span>
                                {tx.dataLabel}{" "}
                                {(data && data.sources) || tx.sources}
                                <span className="ebm-sep2"> · </span>
                                <span className="ebm-rtxt">{tx.refresh}</span>
                            </span>
                            <button
                                type="button"
                                className="ebm-more"
                                onClick={() => setOpen((o) => !o)}
                                aria-expanded={open}
                            >
                                {tx.details}
                                <Chevron dir={open ? "up" : "down"} />
                            </button>
                        </div>
                        {open && (
                            <div className="ebm-details">
                                {[
                                    tx.methodBanking,
                                    tx.methodCompany,
                                    tx.methodRules,
                                    tx.photoNote,
                                    tx.notAdvice,
                                ]
                                    .filter(Boolean)
                                    .map((d, i) => (
                                        <p key={i}>{d}</p>
                                    ))}
                            </div>
                        )}
                    </footer>
                )}
            </div>
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Explanations shown to readers                                       */
/* ------------------------------------------------------------------ */

const PILLAR_INFO: Record<Kind, Record<string, string>> = {
    banking: {
        valuation:
            "Price vs. tangible book value and earnings, compared with peer banks.",
        momentum:
            "Share price trend over 12 months (skipping the last month) and vs. its 200-day average.",
        capital: "CET1 ratio and leverage: the cushion that absorbs losses.",
        quality: "Bad loans (NPL) and provisions: how clean the loan book is.",
        profit: "Return on equity and on assets.",
    },
    company: {
        valuation:
            "Free-cash-flow yield and EV/EBIT, compared with the sector.",
        momentum:
            "Share price trend over 12 months (skipping the last month) and vs. its 200-day average.",
        quality: "Return on invested capital and stability of margins.",
        health: "Debt level (net debt / EBITDA), Piotroski F-score and Altman Z-score.",
    },
}

const GLOSSARY: Record<string, string> = {
    "Pre-tax profit":
        "Profit before tax: what the bank earns from all its activities.",
    "CET1 ratio":
        "Core capital as a share of risk-weighted assets. Higher means a stronger buffer.",
    "Return on equity":
        "Profit earned on shareholders' money. Above 10% is solid for a bank.",
    "Bad loans (NPL)":
        "Loans unlikely to be repaid, as a share of all loans. Lower is better.",
    "Cost / income":
        "Costs per unit of revenue. Lower means a more efficient bank.",
    "Loans / deposits":
        "How much of its deposits the bank lends out. Above 100% means it relies on market funding.",
    "Price / tangible book":
        "Share price vs. net assets per share, excluding goodwill. Below 1 can signal cheapness or worry.",
    Revenue: "Total sales over the year.",
    "Operating profit":
        "Profit from the core business, before interest and tax.",
    "Free cash flow":
        "Cash left after running and investing in the business. It funds dividends, buybacks and debt repayment.",
    "Net debt / EBITDA":
        "Years of operating earnings needed to repay net debt. Below 2 is comfortable.",
    ROIC: "Return on invested capital: how well the company turns capital into profit.",
    "FCF yield":
        "Free cash flow divided by market value. Higher can mean cheaper.",
    "EV / EBIT":
        "Company value (debt included) vs. operating profit. Lower can mean cheaper.",
}

/* ------------------------------------------------------------------ */
/* Sample data (fictional companies, for the design only)              */
/* ------------------------------------------------------------------ */

const BW: [string, string, number][] = [
    ["valuation", "Valuation", 25],
    ["momentum", "Momentum", 25],
    ["capital", "Capital", 20],
    ["quality", "Asset quality", 15],
    ["profit", "Profitability", 15],
]
const CW: [string, string, number][] = [
    ["valuation", "Valuation", 30],
    ["momentum", "Momentum", 30],
    ["quality", "Quality", 20],
    ["health", "Health", 20],
]
function mk(
    w: [string, string, number][],
    s: number[],
    rest: Omit<Item, "pillars" | "score" | "rank">
): Item {
    const pillars = w.map((x, i) => ({
        key: x[0],
        label: x[1],
        weight: x[2],
        score: s[i],
    }))
    const score = Math.round(
        pillars.reduce((a, b) => a + b.score * (b.weight || 0), 0) / 100
    )
    return { ...rest, rank: 0, pillars, score }
}
const rankAll = (arr: Item[], prev: (number | null)[]) =>
    arr
        .sort((a, b) => b.score - a.score)
        .map((it, i) => ({ ...it, rank: i + 1, prevRank: prev[i] }))

const bm = (
    pt: string,
    ptc: number,
    cet: string,
    cetc: number,
    roe: string,
    roec: number,
    npl: string,
    nplc: number,
    ci: string,
    ld: string,
    ptb: string
): Metric[] => [
    {
        label: "Pre-tax profit",
        sub: "Before tax",
        value: pt,
        change: ptc,
        unit: "%",
    },
    {
        label: "CET1 ratio",
        sub: "Core capital strength",
        value: cet,
        change: cetc,
        unit: "pt",
    },
    {
        label: "Return on equity",
        sub: "Profitability",
        value: roe,
        change: roec,
        unit: "pt",
    },
    {
        label: "Bad loans (NPL)",
        sub: "Share of loans",
        value: npl,
        change: nplc,
        unit: "pt",
        good: "down",
    },
    { label: "Cost / income", value: ci },
    { label: "Loans / deposits", value: ld },
    { label: "Price / tangible book", value: ptb },
]
const cm = (
    rv: string,
    rvc: number,
    op: string,
    opc: number,
    fcf: string,
    fcfc: number,
    nd: string,
    ndc: number,
    roic: string,
    fy: string,
    ev: string
): Metric[] => [
    {
        label: "Revenue",
        sub: "Sales over 12 months",
        value: rv,
        change: rvc,
        unit: "%",
    },
    {
        label: "Operating profit",
        sub: "Core business",
        value: op,
        change: opc,
        unit: "%",
    },
    {
        label: "Free cash flow",
        sub: "Cash after investment",
        value: fcf,
        change: fcfc,
        unit: "%",
    },
    {
        label: "Net debt / EBITDA",
        sub: "Debt burden",
        value: nd,
        change: ndc,
        unit: "pt",
        good: "down",
    },
    { label: "ROIC", value: roic },
    { label: "FCF yield", value: fy },
    { label: "EV / EBIT", value: ev },
]

const SAMPLE: Feed = {
    sample: true,
    week: "46",
    asOf: "2026-11-13",
    regime: {
        label: "Risk-on",
        score: 64,
        note: "Trend up, credit spreads calm",
    },
    sources: "SEC EDGAR, EBA, FFIEC, FRED, Wikidata",
    banking: rankAll(
        [
            mk(BW, [88, 81, 86, 78, 80], {
                name: "Northbridge Bank",
                ticker: "NBK",
                exchange: "TSX",
                country: "CA",
                city: "Toronto",
                sector: "Retail and commercial banking",
                employees: 18400,
                website: "northbridge.example",
                why: "Cheap vs. peers, strong capital, rising trend.",
                headline: {
                    label: "Total assets",
                    value: "$412bn",
                    period: "FY 2025",
                },
                ceo: {
                    name: "Elena Marsh",
                    since: 2021,
                    bio: "Former CFO. Focus on cost discipline and digital retail.",
                },
                team: [
                    { role: "CFO", name: "D. Okafor" },
                    { role: "Chair", name: "R. Lindqvist" },
                ],
                metrics: bm(
                    "$6.1bn",
                    8.4,
                    "14.2%",
                    0.6,
                    "13.8%",
                    -0.9,
                    "1.1%",
                    -0.2,
                    "52%",
                    "88%",
                    "1.05"
                ),
                risks: [
                    "Mortgage book exposed to a housing slowdown.",
                    "Margin pressure if rates fall faster than expected.",
                ],
            }),
            mk(BW, [74, 83, 80, 82, 75], {
                name: "Alder Lyon",
                ticker: "ALY",
                exchange: "Euronext",
                country: "FR",
                city: "Lyon",
                sector: "Universal banking",
                employees: 41200,
                website: "alderlyon.example",
                why: "Steady earnings, very few bad loans.",
                headline: {
                    label: "Total assets",
                    value: "$690bn",
                    period: "FY 2025",
                },
                ceo: {
                    name: "Julien Ferrand",
                    since: 2019,
                    bio: "Built the group's insurance arm before taking the top job.",
                },
                team: [
                    { role: "CFO", name: "C. Roux" },
                    { role: "Chair", name: "M. Aubert" },
                ],
                metrics: bm(
                    "$7.4bn",
                    4.1,
                    "13.6%",
                    0.3,
                    "11.2%",
                    0.4,
                    "1.8%",
                    -0.1,
                    "58%",
                    "104%",
                    "0.92"
                ),
                risks: [
                    "Lower rates in the euro area could squeeze income.",
                    "Large exposure to French government bonds.",
                ],
            }),
            mk(BW, [79, 66, 84, 77, 70], {
                name: "Kestrel Savings",
                ticker: "KSV",
                exchange: "TSE",
                country: "JP",
                city: "Osaka",
                sector: "Regional banking",
                employees: 9600,
                website: "kestrel.example",
                why: "Still solid; momentum has cooled.",
                headline: {
                    label: "Total assets",
                    value: "$255bn",
                    period: "FY 2025",
                },
                ceo: {
                    name: "Haruto Sato",
                    since: 2023,
                    bio: "Career banker; leading a push into wealth management.",
                },
                team: [
                    { role: "CFO", name: "Y. Tanaka" },
                    { role: "Chair", name: "K. Mori" },
                ],
                metrics: bm(
                    "$2.3bn",
                    12.6,
                    "15.1%",
                    0.2,
                    "8.9%",
                    1.1,
                    "1.4%",
                    0.1,
                    "61%",
                    "76%",
                    "0.71"
                ),
                risks: [
                    "Profit depends on Bank of Japan rate decisions.",
                    "Ageing customer base in its home region.",
                ],
            }),
            mk(BW, [70, 72, 77, 74, 72], {
                name: "Meridian Nordic Bank",
                ticker: "MNB",
                exchange: "Nasdaq Stockholm",
                country: "SE",
                city: "Stockholm",
                sector: "Universal banking",
                employees: 12800,
                website: "meridian.example",
                why: "Efficient and well capitalised, fairly priced.",
                headline: {
                    label: "Total assets",
                    value: "$318bn",
                    period: "FY 2025",
                },
                ceo: {
                    name: "Sofia Berg",
                    since: 2020,
                    bio: "Previously ran the bank's corporate division.",
                },
                team: [
                    { role: "CFO", name: "A. Nyström" },
                    { role: "Chair", name: "P. Holm" },
                ],
                metrics: bm(
                    "$3.9bn",
                    2.2,
                    "17.4%",
                    -0.4,
                    "14.5%",
                    -0.3,
                    "0.6%",
                    0.0,
                    "41%",
                    "162%",
                    "1.48"
                ),
                risks: [
                    "Heavy reliance on market funding.",
                    "Commercial property exposure in Sweden.",
                ],
            }),
            mk(BW, [66, 75, 70, 71, 74], {
                name: "Coastline Bancorp",
                ticker: "CSTL",
                exchange: "NYSE",
                country: "US",
                city: "Charlotte",
                sector: "Regional banking",
                employees: 22100,
                website: "coastline.example",
                why: "Earnings recovering, share price trending up.",
                headline: {
                    label: "Total assets",
                    value: "$287bn",
                    period: "FY 2025",
                },
                ceo: {
                    name: "Marcus Hale",
                    since: 2022,
                    bio: "Led the turnaround of the bank's consumer lending unit.",
                },
                team: [
                    { role: "CFO", name: "L. Grant" },
                    { role: "Chair", name: "S. Patel" },
                ],
                metrics: bm(
                    "$3.2bn",
                    15.3,
                    "11.3%",
                    0.5,
                    "12.1%",
                    1.6,
                    "0.9%",
                    -0.1,
                    "57%",
                    "86%",
                    "1.62"
                ),
                risks: [
                    "Office property loans remain a watch point.",
                    "Deposit costs could rise again.",
                ],
            }),
        ],
        [null, 2, 1, 4, 3]
    ),
    company: rankAll(
        [
            mk(CW, [72, 91, 88, 84], {
                name: "Veltrix Systems",
                ticker: "VLTX",
                exchange: "Nasdaq",
                country: "US",
                city: "Austin",
                sector: "Technology",
                employees: 36500,
                website: "veltrix.example",
                why: "Strong trend, high returns on capital, fair price.",
                headline: {
                    label: "Market value",
                    value: "$214bn",
                    period: "Nov 13",
                },
                ceo: {
                    name: "Priya Raman",
                    since: 2018,
                    bio: "Co-founder; steered the move to subscription software.",
                },
                team: [
                    { role: "CFO", name: "T. Webb" },
                    { role: "Chair", name: "J. Collins" },
                ],
                metrics: cm(
                    "$48.2bn",
                    14.2,
                    "$11.6bn",
                    18.9,
                    "$9.8bn",
                    22.4,
                    "0.4x",
                    -0.3,
                    "27%",
                    "4.6%",
                    "17.8x"
                ),
                risks: [
                    "Growth expectations are high.",
                    "Regulatory scrutiny of data practices.",
                ],
            }),
            mk(CW, [84, 70, 86, 80], {
                name: "Orrin Pharma",
                ticker: "ORRN",
                exchange: "SIX",
                country: "CH",
                city: "Basel",
                sector: "Health care",
                employees: 51200,
                website: "orrin.example",
                why: "Cheap cash flows and a strong balance sheet.",
                headline: {
                    label: "Market value",
                    value: "$176bn",
                    period: "Nov 13",
                },
                ceo: {
                    name: "Lukas Brenner",
                    since: 2020,
                    bio: "Physician by training; ran the oncology business.",
                },
                team: [
                    { role: "CFO", name: "A. Keller" },
                    { role: "Chair", name: "E. Vogt" },
                ],
                metrics: cm(
                    "$52.7bn",
                    6.1,
                    "$15.9bn",
                    8.3,
                    "$13.1bn",
                    11.0,
                    "0.9x",
                    -0.2,
                    "19%",
                    "7.4%",
                    "11.2x"
                ),
                risks: [
                    "Patent expiry on a key drug in 2028.",
                    "Drug-pricing reforms in the US.",
                ],
            }),
            mk(CW, [76, 82, 74, 78], {
                name: "Kaori Robotics",
                ticker: "KAOR",
                exchange: "TSE",
                country: "JP",
                city: "Nagoya",
                sector: "Industrials",
                employees: 28700,
                website: "kaori.example",
                why: "Orders rising with factory automation demand.",
                headline: {
                    label: "Market value",
                    value: "$61bn",
                    period: "Nov 13",
                },
                ceo: {
                    name: "Aiko Nakamura",
                    since: 2021,
                    bio: "Engineer; previously head of the industrial robot unit.",
                },
                team: [
                    { role: "CFO", name: "S. Ito" },
                    { role: "Chair", name: "T. Fujita" },
                ],
                metrics: cm(
                    "$14.9bn",
                    9.7,
                    "$2.4bn",
                    12.5,
                    "$1.9bn",
                    6.2,
                    "0.2x",
                    0.0,
                    "16%",
                    "3.1%",
                    "19.6x"
                ),
                risks: [
                    "Sales sensitive to the industrial cycle.",
                    "Strong yen would hurt export earnings.",
                ],
            }),
            mk(CW, [80, 68, 72, 76], {
                name: "Lumen Grid",
                ticker: "LMG",
                exchange: "Xetra",
                country: "DE",
                city: "Munich",
                sector: "Utilities",
                employees: 19300,
                website: "lumengrid.example",
                why: "Regulated cash flows at an attractive price.",
                headline: {
                    label: "Market value",
                    value: "$48bn",
                    period: "Nov 13",
                },
                ceo: {
                    name: "Katrin Wolf",
                    since: 2019,
                    bio: "Led the group's grid expansion programme.",
                },
                team: [
                    { role: "CFO", name: "M. Brandt" },
                    { role: "Chair", name: "H. Schulz" },
                ],
                metrics: cm(
                    "$27.4bn",
                    3.8,
                    "$5.1bn",
                    6.6,
                    "$2.2bn",
                    14.8,
                    "3.1x",
                    -0.2,
                    "8%",
                    "4.9%",
                    "13.4x"
                ),
                risks: [
                    "Large investment plan needs funding.",
                    "Regulated returns could be cut.",
                ],
            }),
            mk(CW, [78, 71, 70, 74], {
                name: "Tessaro Foods",
                ticker: "TSRO",
                exchange: "Borsa Italiana",
                country: "IT",
                city: "Milan",
                sector: "Consumer staples",
                employees: 24600,
                website: "tessaro.example",
                why: "Defensive brands, improving margins.",
                headline: {
                    label: "Market value",
                    value: "$39bn",
                    period: "Nov 13",
                },
                ceo: {
                    name: "Giulia Conti",
                    since: 2022,
                    bio: "Former head of the group's international brands.",
                },
                team: [
                    { role: "CFO", name: "F. Marino" },
                    { role: "Chair", name: "R. Greco" },
                ],
                metrics: cm(
                    "$18.3bn",
                    4.4,
                    "$2.6bn",
                    7.9,
                    "$1.8bn",
                    9.5,
                    "1.6x",
                    -0.3,
                    "13%",
                    "4.6%",
                    "15.1x"
                ),
                risks: [
                    "Input costs (cocoa, wheat) remain volatile.",
                    "Private-label competition in Europe.",
                ],
            }),
        ],
        [1, null, 3, 2, 5]
    ),
}

/* ------------------------------------------------------------------ */
/* Styles (same system as Crypto & FX and Metals)                      */
/* ------------------------------------------------------------------ */

const CSS = `
.ebm{width:100%;box-sizing:border-box;background:var(--bg);color:var(--ink);font-family:var(--fb);-webkit-font-smoothing:antialiased}
.ebm *{box-sizing:border-box}
.ebm-wrap{container-type:inline-size;max-width:var(--maxw);margin:0 auto;padding:var(--padt) var(--padx) var(--padb)}
.ebm-row{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 16px}
.ebm-title{font-family:var(--fh);font-size:var(--t1);font-weight:400;line-height:1.2;margin:0}
.ebm-h{font-family:var(--fh);font-size:var(--t2);font-weight:400;line-height:1.2;margin:0}
.ebm-meta{font-size:11px;color:var(--mute)}
.ebm-clock{display:inline-flex;align-items:center;gap:6px;font-variant-numeric:tabular-nums}
.ebm-dot{width:6px;height:6px;border-radius:50%;background:var(--mute);flex:none}
.ebm-dot.is-live{background:var(--up);animation:ebmPulse 1.8s ease-in-out infinite}
@keyframes ebmPulse{0%,100%{opacity:1}50%{opacity:.3}}
.ebm-subt{margin:6px 0 0;font-size:12px;line-height:1.5;color:var(--mute)}
.ebm-strip{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:6px 20px;margin-top:14px;padding:7px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);font-size:13px}
.ebm-strip b{font-family:var(--fh);font-weight:400;font-size:15px}
.ebm-lab,.ebm-caps{font-size:9.5px;font-weight:500;letter-spacing:.05em;text-transform:uppercase;color:var(--mute)}
.ebm-sample{font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:var(--dn);border:1px solid currentColor;padding:2px 6px}
.ebm .up{color:var(--up)}.ebm .dn{color:var(--dn)}.ebm .flat{color:var(--mute)}
.ebm-note{margin:16px 0 0;font-size:12px;color:var(--mute)}
.ebm-note.is-err{color:var(--dn)}
.ebm .num{font-family:var(--fh);font-variant-numeric:tabular-nums lining-nums}

.ebm-sec{margin-top:var(--secgap)}
.ebm-sechead{margin-bottom:10px}
.ebm-monitors{display:flex;gap:0 32px;margin-top:var(--secgap);border-bottom:1px solid var(--strong)}
.ebm-mon{appearance:none;border:0;background:none;margin:0 0 -1px;padding:0 0 10px;cursor:pointer;font-family:var(--fh);font-size:calc(var(--t2) + 2px);font-weight:400;line-height:1.2;color:var(--mute);border-bottom:2px solid transparent;transition:color .15s,border-color .15s}
.ebm-mon:hover{color:var(--ink)}
.ebm-mon.is-on{color:var(--ink);border-bottom-color:var(--ink);cursor:default}
.ebm-mon:focus-visible{outline:1px solid var(--link);outline-offset:4px}
.ebm-sec.is-switched{margin-top:12px}
.ebm-toolbar{display:flex;justify-content:space-between;align-items:center;gap:8px 16px;flex-wrap:wrap;margin:0 0 10px;min-height:30px}
.ebm-tabs{display:inline-flex;align-items:baseline;flex-wrap:wrap;gap:5px;font-size:12px}
.ebm-tabs button{appearance:none;border:0;background:none;padding:0;margin:0;cursor:pointer;font:inherit;color:var(--link)}
.ebm-tabs button:hover{text-decoration:underline}
.ebm-tabs button[aria-pressed="true"]{color:var(--ink);font-weight:700;text-decoration:none;cursor:default}
.ebm-sep{color:var(--mute)}

/* cards */
.ebm-card{height:100%;display:flex;flex-direction:column;border-top:1px solid var(--strong);padding:12px 0 8px;outline:none}
.ebm-card.is-click{cursor:pointer}
.ebm-card:hover .ebm-name{color:var(--link)}
.ebm-card.is-sel{border-top:2px solid var(--link);padding-top:11px}
.ebm-card:focus-visible{outline:1px solid var(--link);outline-offset:3px}
.ebm-ctop{display:flex;justify-content:space-between;align-items:baseline}
.ebm-rank{font-family:var(--fh);font-size:calc(var(--big) * 1.1);line-height:1}
.ebm-move{font-size:11px;white-space:nowrap}
.ebm-id{display:flex;align-items:center;gap:10px;margin-top:12px;min-width:0}
.ebm-idtxt{min-width:0}
.ebm-name{font-family:var(--fh);font-size:calc(var(--t2) - 2px);line-height:1.25;color:var(--ink);transition:color .15s}
.ebm-sub{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--mute);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ebm-scorerow{display:flex;justify-content:space-between;align-items:baseline;margin-top:14px;padding-top:8px;border-top:1px solid var(--rule)}
.ebm-score{font-family:var(--fh);font-size:var(--big);line-height:1;font-variant-numeric:tabular-nums lining-nums}
.ebm-score small,.ebm-bigscore small{font-family:var(--fb);font-size:11px;color:var(--mute)}
.ebm-bars{margin-top:4px}
.ebm-bar{display:grid;grid-template-columns:minmax(0,96px) minmax(0,1fr) 26px;align-items:center;gap:12px;padding:5px 0}
.ebm-barlab{font-size:11px;color:var(--mute);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ebm-bar .num{font-size:13px;text-align:right;color:var(--ink)}
.ebm-meter{position:relative;display:block;height:7px;min-width:40px}
.ebm-meter::before{content:"";position:absolute;left:0;right:0;top:3px;height:1px;background:var(--rule)}
.ebm-meter i{position:absolute;left:0;top:3px;height:1px;background:var(--ink)}
.ebm-meter b{position:absolute;top:1px;width:5px;height:5px;margin-left:-2.5px;border-radius:50%;background:var(--ink)}
.ebm-meter s{position:absolute;left:50%;top:0;width:1px;height:7px;background:var(--mute);opacity:.6}
.ebm-meter.is-lg{height:9px}
.ebm-meter.is-lg::before,.ebm-meter.is-lg i{top:4px}
.ebm-meter.is-lg b{top:1px;width:7px;height:7px;margin-left:-3.5px}
.ebm-meter.is-lg s{height:9px}
.ebm-why{font-size:12px;line-height:1.5;color:var(--strong);margin:12px 0 0}
.ebm-open{display:inline-flex;align-items:center;gap:5px;margin-top:auto;padding-top:12px;font-size:12px;color:var(--link)}
.ebm-card.is-big .ebm-rank{font-size:calc(var(--big) * 1.5)}
.ebm-card.is-big .ebm-name{font-size:var(--t2)}
.ebm-card.is-big .ebm-score{font-size:calc(var(--big) * 1.25)}

.ebm-mark{display:inline-flex;flex:none;align-items:center;justify-content:center;overflow:hidden;background:var(--ink);color:var(--bg);font-family:var(--fh);letter-spacing:.02em;line-height:1}
.ebm-mark.is-img{background:transparent;box-shadow:none}
.ebm-mark img{display:block;width:100%;height:100%;object-fit:cover}
.ebm-mark.is-logo{background:transparent}
.ebm-mark.is-logo img{object-fit:contain;padding:0}
.ebm-flag{display:inline-flex;flex:none;align-items:center;justify-content:center;border-radius:50%;overflow:hidden;position:relative;background:var(--rule)}
.ebm-flag img{display:block;width:100%;height:100%;object-fit:cover}
.ebm-flag::after{content:"";position:absolute;inset:0;border-radius:50%;box-shadow:inset 0 0 0 1px rgba(0,0,0,.12)}
.ebm-flag-txt{font-weight:700;color:var(--mute)}

/* carousel */
.ebm-carousel{position:relative}
.ebm-nav{display:flex;align-items:center;gap:6px;margin-left:auto}
.ebm-count{font-size:11px;color:var(--mute);margin-right:6px;font-variant-numeric:tabular-nums}
.ebm-arrow{appearance:none;width:30px;height:30px;margin:0;padding:0;border:1px solid var(--rule);border-bottom-color:var(--strong);border-radius:0;background:transparent;color:var(--link);cursor:pointer;display:inline-flex;align-items:center;justify-content:center}
.ebm-arrow:hover{border-color:var(--strong)}
.ebm-arrow[data-off]{color:var(--mute);opacity:.45;cursor:default}
.ebm-track{display:grid;grid-auto-flow:column;grid-auto-columns:calc((100% - (var(--vis) - 1) * var(--gap)) / var(--vis));gap:0 var(--gap);overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x mandatory;scrollbar-width:none;-webkit-overflow-scrolling:touch;position:relative}
.ebm-track::-webkit-scrollbar{display:none}
.ebm-slot{scroll-snap-align:start;min-width:0}

/* ranking table */
.ebm-tbl{width:100%;border-collapse:collapse;font-size:var(--row)}
.ebm-tbl th{font-size:9.5px;font-weight:500;letter-spacing:.04em;text-transform:uppercase;color:var(--mute);text-align:left;padding:0 12px 5px;border-bottom:1px solid var(--strong);white-space:nowrap}
.ebm-tbl td{padding:8px 12px;border-bottom:1px solid var(--rule);vertical-align:middle}
.ebm-tbl th:first-child,.ebm-tbl td:first-child{padding-left:0}
.ebm-tbl th:last-child,.ebm-tbl td:last-child{padding-right:0}
.ebm-tbl .r{text-align:right}
.ebm-tbl .c-rank{width:34px;font-size:calc(var(--row) + 3px)}
.ebm-tbl .c-score{width:150px}
.ebm-tbl .c-move{width:110px}
.ebm-tbl tr.is-click{cursor:pointer}
.ebm-tbl tr.is-click:hover .ebm-tn{color:var(--link)}
.ebm-tbl tr.is-sel td{background:color-mix(in srgb,var(--link) 8%,transparent)}
.ebm-tbl tr.is-sel td:first-child{box-shadow:inset 2px 0 0 var(--link);padding-left:8px}
.ebm-tbl tr:focus-visible{outline:1px solid var(--link);outline-offset:-1px}
.ebm-tname{display:inline-flex;align-items:center;gap:10px}
.ebm-tn{display:block;font-family:var(--fh);font-size:calc(var(--row) + 1px)}
.ebm-tscore{display:flex;align-items:center;gap:10px}
.ebm-tscore .num{font-size:calc(var(--row) + 3px);width:28px}
.ebm-tscore .ebm-meter{flex:1}
.ebm-tbl.is-compact .c-score{width:120px}

/* spotlight */
.ebm-spot{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:0 36px;align-items:start}
.ebm-spot-r{border-top:1px solid var(--strong);padding-top:10px}

/* detail */
.ebm-detail{margin-top:26px;border-top:2px solid var(--link);padding-top:16px}
.ebm-dhead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px 24px;flex-wrap:wrap}
.ebm-dhl{display:flex;align-items:center;gap:14px;min-width:0}
.ebm-dname{font-family:var(--fh);font-size:calc(var(--t1) + 2px);font-weight:400;line-height:1.15;margin:0 0 4px}
.ebm-dhr{text-align:right}
.ebm-hval{font-family:var(--fh);font-size:calc(var(--big) * .95);line-height:1.1;font-variant-numeric:tabular-nums lining-nums}
.ebm-dmeta{display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px 16px;margin-top:12px;font-size:12px;color:var(--mute)}
.ebm-dmeta-l{display:inline-flex;flex-wrap:wrap;gap:4px 16px}
.ebm-link{color:var(--link);text-decoration:none}
.ebm-link:hover{text-decoration:underline}
.ebm-dtabs{display:flex;justify-content:space-between;align-items:center;margin:14px 0 18px;padding-bottom:8px;border-bottom:1px solid var(--strong)}
.ebm-x{appearance:none;border:0;background:none;cursor:pointer;font-size:20px;line-height:1;color:var(--mute);padding:0 2px}
.ebm-x:hover{color:var(--ink)}
.ebm-dgrid{display:grid;grid-template-columns:minmax(0,4fr) minmax(0,7fr);gap:0 36px;align-items:start}
.ebm-dleft,.ebm-dright{border-top:1px solid var(--strong);padding-top:12px}
.ebm-ceo{display:flex;align-items:center;gap:12px;margin-top:12px}
.ebm-ceoname{font-family:var(--fh);font-size:var(--t2)}
.ebm-credit{font-size:10px;color:var(--mute);margin-top:6px}
.ebm-bio{font-size:13px;line-height:1.55;color:var(--strong);margin:12px 0 0}
.ebm-mini{width:100%;border-collapse:collapse;font-size:13px;margin-top:14px}
.ebm-mini td{padding:5px 0;border-bottom:1px solid var(--rule)}
.ebm-mini tr:first-child td{border-top:1px solid var(--rule)}
.ebm-mini td:first-child{color:var(--mute);font-size:12px}
.ebm-mini .r{text-align:right}
.ebm-whybox{margin-top:18px}
.ebm-whybox p{font-family:var(--fh);font-size:15px;line-height:1.45;margin:6px 0 0}
.ebm-metrics{margin-top:4px}
.ebm-m{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:11px 0;border-bottom:1px solid var(--rule)}
.ebm-mlab{display:block;font-size:14px}
.ebm-msub{display:block;font-size:11px;color:var(--mute);margin-top:2px;line-height:1.45}
.ebm-mval{text-align:right;flex:none}
.ebm-mnum{display:block;font-family:var(--fh);font-size:calc(var(--big) * .85);line-height:1.1;font-variant-numeric:tabular-nums lining-nums}
.ebm-chg{font-size:11px;white-space:nowrap;font-variant-numeric:tabular-nums}
.ebm-bigscore{font-family:var(--fh);font-size:calc(var(--big) * 2);line-height:1;margin-top:10px}
.ebm-pillars{margin-top:4px}
.ebm-pil{padding:10px 0;border-bottom:1px solid var(--rule)}
.ebm-pilhead{display:flex;justify-content:space-between;font-size:14px}
.ebm-pilbar{display:flex;align-items:center;gap:12px;margin-top:6px}
.ebm-pilbar .ebm-meter{flex:1}
.ebm-pilbar .num{width:26px;text-align:right;font-size:15px}
.ebm-fintbl .c-note{font-size:12px;color:var(--mute);line-height:1.45;white-space:normal;min-width:200px}
.ebm-fintbl td.num{font-size:calc(var(--row) + 1px);white-space:nowrap}
.ebm-risks{margin:0;padding:0 0 0 18px;font-size:14px;line-height:1.6}
.ebm-risks li{padding:4px 0}

/* footer */
.ebm-foot{margin-top:calc(var(--secgap) * .9);font-size:var(--fsz);line-height:1.5;color:var(--mute)}
.ebm-refresh{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:4px 16px}
.ebm-rtxt{color:var(--link)}
.ebm-more{appearance:none;border:0;background:none;padding:0;margin:0;cursor:pointer;font:inherit;color:var(--link);display:inline-flex;align-items:center;gap:5px}
.ebm-more:hover{text-decoration:underline}
.ebm-details{margin-top:8px;padding-top:8px;border-top:1px solid var(--rule)}
.ebm-details p{margin:0 0 6px}

@media (prefers-reduced-motion:reduce){.ebm-dot.is-live{animation:none}.ebm-name{transition:none}}
@container (max-width:900px){
  .ebm-track{grid-auto-columns:calc((100% - 1.2 * var(--gap)) / 2.2)}
  .ebm-spot,.ebm-dgrid{grid-template-columns:minmax(0,1fr)}
  .ebm-spot-r{margin-top:22px}
  .ebm-dright{order:-1;margin-bottom:22px}
  .ebm-tbl .c-pil{display:none}
}
@container (max-width:560px){
  .ebm-monitors{gap:0 20px}
  .ebm-mon{font-size:var(--t2)}
  .ebm-track{grid-auto-columns:calc((100% - .25 * var(--gap)) / 1.25)}
  .ebm-count{display:none}
  .ebm-dhr{text-align:left}
  .ebm-tbl .c-score{width:96px}
  .ebm-tbl .c-move{width:auto}
  .ebm-tscore .ebm-meter{display:none}
  .ebm-fintbl .c-note{display:none}
  .ebm-refresh{flex-direction:column}
}
`

/* ------------------------------------------------------------------ */
/* Framer properties                                                   */
/* ------------------------------------------------------------------ */

const DEF_TEXTS: Record<string, string> = {
    title: "EB Monitor",
    subtitle:
        "Each week, the five banks and five companies that score best on the EB Method: a transparent mix of value, trend, strength and quality.",
    newYork: "New York",
    nextUpdate: "Next update",
    inTime: "in {t}",
    regime: "EB Market Regime",
    sampleBadge: "Sample data · fictional companies",
    loading: "Loading this week's ranking…",
    unavailable:
        "This week's ranking is temporarily unavailable. Please check back soon.",
    empty: "No ranking this week.",
    monitors: "Monitors",
    bankingTitle: "Banking Monitor",
    bankingNote: "Top 5 banks ranked by the EB Method",
    companyTitle: "Company Monitor",
    companyNote: "Top 5 companies ranked by the EB Method",
    weekLabel: "Week",
    view: "View",
    viewCards: "Cards",
    viewRanking: "Ranking",
    showing: "{a}–{b} of {n}",
    prev: "Previous",
    next: "Next",
    score: "EB Score",
    name: "Name",
    week: "This week",
    moveNew: "New",
    moveHeld: "= Held",
    moveFrom: "from {n}",
    open: "Full analysis",
    close: "Close",
    analysis: "Analysis",
    tOverview: "Overview",
    tScore: "EB Score",
    tFinancials: "Financials",
    tRisks: "Risks",
    employees: "employees",
    leadership: "Leadership",
    ceo: "Chief Executive Officer",
    since: "since",
    photo: "Photo:",
    noCeo: "Leadership data not available.",
    whyTitle: "Why it's here",
    keyMetrics: "Key metrics",
    vsPrior: "vs. prior year",
    pillars: "What makes the score",
    weight: "Weight",
    scoreHint:
        "Each pillar is scored from 0 to 100 against sector peers; the tick marks 50, the peer median. The EB Score is their weighted average.",
    metric: "Metric",
    value: "Value",
    change: "Change",
    meaning: "What it means",
    dataLabel: "Data:",
    sources: "SEC EDGAR, EBA, FFIEC, FRED, Wikidata",
    refresh: "Updated weekly, Monday 7:00 am New York",
    details: "Method & disclaimer",
    methodBanking:
        "Banking Monitor: listed banks worth more than $10bn, scored on Valuation (25%), Momentum (25%), Capital (20%), Asset quality (15%) and Profitability (15%).",
    methodCompany:
        "Company Monitor: listed non-financial companies worth more than $10bn, scored on Valuation (30%), Momentum (30%), Quality (20%) and Financial health (20%).",
    methodRules:
        "Scores compare each company with its sector peers. To limit weekly noise, a pick keeps its place while it stays in the top 10, and no more than two picks may come from the same country or sector.",
    photoNote:
        "Portraits come from Wikimedia Commons under free licences; the photographer is credited under each photo.",
    notAdvice:
        "The EB Monitor is educational content ranked by a published method. It is not investment advice or a recommendation to buy or sell. Past scores do not predict future returns, and you may lose money investing.",
}

const DEFAULTS: Record<string, any> = {
    dataUrl: "",
    showHeader: true,
    showClock: true,
    showRegime: true,
    showBanking: true,
    showCompany: true,
    showFooter: true,
    startWith: "banking",
    bankingLayout: "carousel",
    companyLayout: "carousel",
    cardsVisible: 3,
    cardBars: 3,
    showWhy: true,
    readerSwitch: true,
    scrollToDetail: true,
    logoSize: 36,
    maxWidth: 1040,
    padding: 24,
    spaceTop: 24,
    spaceBottom: 24,
    sectionGap: 44,
    cardGap: 24,
    titleSize: 22,
    sectionTitleSize: 18,
    rowSize: 15,
    scoreSize: 28,
    footerSize: 11,
    background: "#F0E6DC",
    ink: "#1A1A1A",
    muted: "#7A736C",
    rule: "#D9CFC4",
    strongRule: "#57514B",
    link: "#1F6FC5",
    upColor: "#1A8F3C",
    downColor: "#D0021B",
    texts: DEF_TEXTS,
}

EBMonitor.defaultProps = DEFAULTS

const num = (
    title: string,
    min: number,
    max: number,
    step = 1,
    extra: any = {}
) => ({
    type: ControlType.Number,
    title,
    min,
    max,
    step,
    ...extra,
})
const LAYOUT = {
    type: ControlType.Enum,
    options: ["carousel", "row", "spotlight", "ranking"],
    optionTitles: ["Carousel", "Row", "Spotlight", "Ranking"],
}

const CONTROLS: Record<string, any> = {
    /* Data */
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        placeholder: "Empty = sample data",
        description:
            "Link to eb-monitor.json published by the EB engine. Leave empty to see the fictional sample.",
    },

    /* Sections */
    showHeader: { type: ControlType.Boolean, title: "Header" },
    showClock: {
        type: ControlType.Boolean,
        title: "· New York clock",
        hidden: (p: any) => !p.showHeader,
    },
    showRegime: {
        type: ControlType.Boolean,
        title: "· Market regime",
        hidden: (p: any) => !p.showHeader,
    },
    showBanking: { type: ControlType.Boolean, title: "Banking" },
    bankingLayout: {
        ...LAYOUT,
        title: "· Banking layout",
        hidden: (p: any) => !p.showBanking,
    },
    showCompany: { type: ControlType.Boolean, title: "Company" },
    companyLayout: {
        ...LAYOUT,
        title: "· Company layout",
        hidden: (p: any) => !p.showCompany,
    },
    startWith: {
        type: ControlType.Enum,
        title: "Opens on",
        options: ["banking", "company"],
        optionTitles: ["Banking", "Company"],
        displaySegmentedControl: true,
        description:
            "Readers switch between the two monitors at the top. Links ending in #company-monitor open Company directly.",
        hidden: (p: any) => !p.showBanking || !p.showCompany,
    },
    showFooter: { type: ControlType.Boolean, title: "Footer" },

    /* Cards */
    cardsVisible: {
        ...num("Cards visible", 1, 5, 1),
        description:
            "Carousel on desktop. Tablet shows 2 and a bit, mobile 1 and a bit.",
    },
    cardBars: {
        ...num("Bars on card", 0, 5, 1),
        description: "How many score pillars each card shows.",
    },
    showWhy: { type: ControlType.Boolean, title: "“Why” line" },
    readerSwitch: {
        type: ControlType.Boolean,
        title: "Reader switch",
        description: "Lets readers switch between Cards and Ranking.",
    },
    scrollToDetail: {
        type: ControlType.Boolean,
        title: "Scroll to analysis",
        description:
            "Brings the full analysis into view when a card is opened.",
    },
    logoSize: num("Logo size", 24, 64, 1, { unit: "px" }),

    /* Spacing */
    maxWidth: num("Max width", 320, 1600, 10, {
        unit: "px",
        description: "Content is centred and never wider than this.",
    }),
    padding: num("Side padding", 0, 120, 1, { unit: "px" }),
    spaceTop: num("Space top", 0, 240, 1, { unit: "px" }),
    spaceBottom: num("Space bottom", 0, 240, 1, { unit: "px" }),
    sectionGap: num("Section gap", 0, 160, 1, { unit: "px" }),
    cardGap: num("Card gap", 8, 60, 1, { unit: "px" }),

    /* Sizes */
    titleSize: num("Title size", 14, 64),
    sectionTitleSize: num("Section size", 12, 40),
    rowSize: num("Row text", 11, 22),
    scoreSize: num("Score size", 16, 60),
    footerSize: num("Footer text", 9, 18, 0.5, { unit: "px" }),

    /* Fonts & colours */
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
    link: { type: ControlType.Color, title: "Links" },
    upColor: { type: ControlType.Color, title: "Good / up" },
    downColor: { type: ControlType.Color, title: "Bad / down" },

    /* Texts */
    texts: {
        type: ControlType.Object,
        title: "Texts",
        description: "Edit any text. Leave a field empty to remove that text.",
        controls: Object.fromEntries(
            Object.keys(DEF_TEXTS).map((k) => [
                k,
                {
                    type: ControlType.String,
                    title: k
                        .replace(/([A-Z])/g, " $1")
                        .replace(/^./, (c) => c.toUpperCase()),
                    defaultValue: DEF_TEXTS[k],
                    ...(DEF_TEXTS[k].length > 60
                        ? { displayTextArea: true }
                        : {}),
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
addPropertyControls(EBMonitor, CONTROLS)

/* ------------------------------------------------------------------ */
/* Flags: country-flag-icons (MIT License, (c) 2020 catamphetamine),   */
/* same set as the Crypto & FX component, plus simple euro-area flags. */
/* Built in: no network.                                               */
/* ------------------------------------------------------------------ */

const FLAG_SVG: Record<string, string> = {
    US: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="59.85 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><g fill="#D80027"><path d="M0 0h513v26.3H0zM0 52.6h513v26.3H0zM0 105.2h513v26.3H0zM0 157.8h513v26.3H0zM0 210.5h513v26.3H0zM0 263.1h513v26.3H0zM0 315.7h513V342H0z"/></g><path fill="#2E52B2" d="M0 0h256.5v184.1H0z"/><g fill="#FFF"><path d="m47.8 138.9-4-12.8-4.4 12.8H26.2l10.7 7.7-4 12.8 10.9-7.9 10.6 7.9-4.1-12.8 10.9-7.7zM104.1 138.9l-4.1-12.8-4.2 12.8H82.6l10.7 7.7-4 12.8 10.7-7.9 10.8 7.9-4-12.8 10.7-7.7zM160.6 138.9l-4.3-12.8-4 12.8h-13.5l11 7.7-4.2 12.8 10.7-7.9 11 7.9-4.2-12.8 10.7-7.7zM216.8 138.9l-4-12.8-4.2 12.8h-13.3l10.8 7.7-4 12.8 10.7-7.9 10.8 7.9-4.3-12.8 11-7.7zM100 75.3l-4.2 12.8H82.6L93.3 96l-4 12.6 10.7-7.8 10.8 7.8-4-12.6 10.7-7.9h-13.4zM43.8 75.3l-4.4 12.8H26.2L36.9 96l-4 12.6 10.9-7.8 10.6 7.8L50.3 96l10.9-7.9H47.8zM156.3 75.3l-4 12.8h-13.5l11 7.9-4.2 12.6 10.7-7.8 11 7.8-4.2-12.6 10.7-7.9h-13.2zM212.8 75.3l-4.2 12.8h-13.3l10.8 7.9-4 12.6 10.7-7.8 10.8 7.8-4.3-12.6 11-7.9h-13.5zM43.8 24.7l-4.4 12.6H26.2l10.7 7.9-4 12.7L43.8 50l10.6 7.9-4.1-12.7 10.9-7.9H47.8zM100 24.7l-4.2 12.6H82.6l10.7 7.9-4 12.7L100 50l10.8 7.9-4-12.7 10.7-7.9h-13.4zM156.3 24.7l-4 12.6h-13.5l11 7.9-4.2 12.7 10.7-7.9 11 7.9-4.2-12.7 10.7-7.9h-13.2zM212.8 24.7l-4.2 12.6h-13.3l10.8 7.9-4 12.7 10.7-7.9 10.8 7.9-4.3-12.7 11-7.9h-13.5z"/></g></svg>',
    CA: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><g fill="red"><path d="M0 0h142v342H0zM371 0h142v342H371zM306.5 206l50.4-25.2-25.2-12.6V143l-50.4 25.2 25.2-50.4h-25.2L256.1 80l-25.2 37.8h-25.2l25.2 50.4-50.4-25.2v25.2l-25.2 12.6 50.4 25.2-12.6 25.2h50.4V269h25.2v-37.8h50.4z"/></g></svg>',
    GB: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><g fill="#FFF"><path d="M0 0h513v341.3H0V0z"/><path d="M311.7 230 513 341.3v-31.5L369.3 230h-57.6zM200.3 111.3 0 0v31.5l143.7 79.8h56.6z"/></g><g fill="#012169"><path d="M393.8 230 513 295.7V230H393.8zm-82.1 0L513 341.3v-31.5L369.3 230h-57.6zm146.9 111.3-147-81.7v81.7h147zM90.3 230 0 280.2V230h90.3zm110 14.2v97.2H25.5l174.8-97.2zM118.2 111.3 0 45.6v65.7h118.2zm82.1 0L0 0v31.5l143.7 79.8h56.6zM53.4 0l147 81.7V0h-147zM421.7 111.3 513 61.1v50.2h-91.3zm-110-14.2V0h174.9L311.7 97.1z"/></g><g fill="#c8102e"><path d="M288 0h-64v138.7H0v64h224v138.7h64V202.7h224v-64H288V0z"/><path d="M311.7 230 513 341.3v-31.5L369.3 230h-57.6zM143.7 230 0 309.9v31.5L200.3 230h-56.6zM200.3 111.3 0 0v31.5l143.7 79.8h56.6zM368.3 111.3 513 31.5V0L311.7 111.3h56.6z"/></g></svg>',
    CH: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="128 0 512 512"><path fill="red" d="M0 0h768v512H0V0z"/><path fill="#FFF" d="M336 96h96v112h112v96H432v112h-96V304H224v-96h112V96z"/></svg>',
    JP: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FFF" d="M0 0h512v342H0z"/><circle fill="#D80027" cx="256.5" cy="171" r="96"/></svg>',
    AU: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#00008b" d="M0 0h513v342H0z"/><g fill="#FFF"><path d="m188 212.6 11 22.9 24.7-5.7-11 22.8 19.9 15.8-24.8 5.6.1 25.4-19.9-15.9-19.8 15.9.1-25.4-24.8-5.6 19.9-15.8-11.1-22.8 24.8 5.7zM385.9 241.1l5.2 10.9 11.8-2.7-5.3 10.9 9.5 7.5-11.8 2.6v12.2l-9.4-7.6-9.5 7.6.1-12.2-11.8-2.6 9.5-7.5-5.3-10.9 11.8 2.7zM337.3 125.1l5.2 10.9 11.8-2.7-5.3 10.9 9.5 7.5-11.8 2.7v12.1l-9.4-7.6-9.5 7.6.1-12.1-11.9-2.7 9.5-7.5-5.3-10.9L332 136zM385.9 58.9l5.2 10.9 11.8-2.7-5.3 10.9 9.5 7.5-11.8 2.7v12.1l-9.4-7.6-9.5 7.6.1-12.1-11.8-2.7 9.5-7.5-5.3-10.9 11.8 2.7zM428.4 108.6l5.2 10.9 11.8-2.7-5.3 10.9 9.5 7.5-11.8 2.6V150l-9.4-7.6-9.5 7.6v-12.2l-11.8-2.6 9.5-7.5-5.3-10.9 11.8 2.7zM398 166.5l4.1 12.7h13.3l-10.8 7.8 4.2 12.7-10.8-7.9-10.8 7.9 4.1-12.7-10.7-7.8h13.3z"/></g><path fill="#00008b" d="M0 0h256.5v171H0z"/><g fill="#FFF"><path d="M256.5 0v30.6l-45.3 25.2h45.3v59.4h-59.2l59.2 32.9V171h-26.7l-73.7-40.9V171h-55.7v-48.7L12.8 171H0v-30.6l45.3-25.2H0V55.8h59.2L0 22.9V0h26.7l73.7 40.9V0h55.7v48.7L243.7 0z"/><path d="M156.1 115.2 256.5 171v-15.8l-72-40zM100.4 55.8 0 0v15.8l72 40z"/></g><g fill="red"><path d="M144.3 0h-32.1v69.5H0v32h112.2V171h32.1v-69.5h112.2v-32H144.3z"/><path d="M156.1 115.2 256.5 171v-15.8l-72-40zM72 115.2l-72 40V171l100.4-55.8zM100.4 55.8 0 0v15.8l72 40zM184.5 55.8l72-40V0L156.1 55.8z"/></g></svg>',
    SE: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="30.78 0 342 342"><path fill="#004F8E" d="M0 0h513v342H0z"/><path fill="#F6C500" d="M192.4.3h-64.2v138.8H0v64.1h128.2V342h64.2V203.2H513v-64.1H192.4z"/></svg>',
    DK: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="23.94 0 342 342"><path fill="#c60c30" d="M0 0h513v342H0z"/><path fill="#FFF" d="M190 0h-60v140H0v60h130v142h60V200h323v-60H190z"/></svg>',
    NO: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="37.62 0 342 342"><path fill="#ba0c2f" d="M0 0h513v342H0z"/><path fill="#FFF" d="M513 211H202.6v131h-79.9V211H0v-80h122.7V0h79.9v131H513v61.4z"/><path fill="#00205b" d="M513 149.6v42.8H184V342h-42.7V192.4H0v-42.8h141.3V0H184v149.6z"/></svg>',
    SG: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600"><path fill="#FFF" d="M0 0h900v600H0V0z"/><path fill="#ED2939" d="M0 0h900v300H0V0z"/><g fill="#FFF"><path d="M129.7 150c0-48.8 29-90.9 70.6-109.9-3.4-.3-6.8-.5-10.2-.5-61 0-110.4 49.4-110.4 110.4s49.4 110.4 110.4 110.4c3.4 0 6.9-.2 10.2-.5-41.7-19-70.6-61.1-70.6-109.9zM260.9 90.1l16.9-12.3H257l-6.5-19.9-6.5 19.9h-20.8l16.9 12.3-6.5 19.8 16.9-12.3 16.9 12.3zM298.2 204.6l16.9-12.2h-20.9l-6.5-19.9-6.4 19.9h-20.9l16.9 12.2-6.5 19.9 16.9-12.3 16.9 12.3z"/><path d="m200.7 133.8 16.9-12.3h-20.9l-6.4-19.8-6.5 19.8h-20.9l16.9 12.3-6.4 19.9 16.9-12.3 16.9 12.3zM338.1 121.5h-20.9l-6.5-19.8-6.4 19.8h-20.9l16.9 12.3-6.5 19.9 16.9-12.3 16.9 12.3-6.4-19.9zM223.7 204.6l16.9-12.2h-20.9l-6.4-19.9-6.5 19.9h-20.9l16.9 12.2-6.4 19.9 16.9-12.3 16.9 12.3z"/></g></svg>',
    HK: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="3.5 0 14 14"><path fill="#FFF" d="M0 0h21v14H0V0z"/><path fill="#EE1C25" d="M0 0h21v14H0V0z"/><path fill="#FFF" d="M12 6.7c-.8-.5-1 .4-1 0 0-.8.9-1.5 2-1.5s2 .7 2 1.5c-.9 0-1 .5-1.5.5-.6 0-.7 0-1.5-.5zm1.2-.2c.1 0 .2-.1.2-.2s0-.3-.2-.3-.2.1-.2.2.1.3.2.3zm-1.8 2c.2-.9-.7-.8-.3-.9.8-.3 1.7.4 2 1.4.3 1.1 0 2.1-.8 2.4-.3-.9-.8-.8-.9-1.3-.1-.6-.2-.7 0-1.6zm.6 1.1c0 .1.2.2.3.2.1 0 .2-.2.2-.3s-.2-.2-.3-.2c-.2 0-.2.2-.2.3zM9.6 8.5c.9-.1.6-.9.8-.6.5.7.2 1.7-.7 2.4-.9.6-2 .6-2.5 0 .8-.6.6-1 .9-1.3.4-.4.5-.5 1.5-.5zm-.9.9c-.1 0-.2.2-.1.3s.3.2.4.1.1-.3 0-.4-.2-.1-.3 0zM9 6.7c.3.9 1 .3.8.6-.5.7-1.6.7-2.5 0-.9-.6-1.2-1.7-.7-2.4.8.6 1.1.2 1.5.5.4.4.5.4.9 1.3zm-1.1-.6c-.1-.1-.3 0-.4.1s-.1.3 0 .4c.1.1.3 0 .3-.1.2-.1.2-.3.1-.4zm2.6-.5c-.7.6.1 1.1-.3 1-.8-.3-1.2-1.4-.8-2.4.3-1 1.3-1.7 2-1.4-.3.9.2 1.1 0 1.6-.1.5-.2.6-.9 1.2zm.2-1.2c0-.1 0-.3-.1-.3s-.3 0-.3.1 0 .3.2.3c0 .1.1 0 .2-.1z"/></svg>',
    IN: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#ff6820" d="M0 0h513v114H0V0z"/><path fill="#FFF" d="M0 114h513v114H0V114z"/><path fill="#046a38" d="M0 228h513v114H0V228z"/><path fill="none" stroke="#07038d" stroke-width="4" d="M256.5 136.8c18.9 0 34.2 15.3 34.2 34.2s-15.3 34.2-34.2 34.2-34.2-15.3-34.2-34.2 15.3-34.2 34.2-34.2z"/><g stroke="#07038d" stroke-width="2"><path d="m265.3 138.2-17.6 65.7m17.6-65.7-17.6 65.7M273.5 141.6l-34 58.9M280.5 147l-48 48M285.9 154 227 188M289.3 162.2l-65.7 17.6M290.5 171h-68M289.3 179.8l-65.7-17.6M285.9 188 227 154M280.5 195l-48-48M273.5 200.4l-34-58.9M265.3 203.8l-17.6-65.7M256.5 205v-68M247.7 203.8l17.6-65.7M239.5 200.4l34-58.9M232.5 195l48.1-48.1M227.1 188l58.9-34M223.7 179.8l65.7-17.6M222.5 171h68M223.7 162.2l65.7 17.6M227.1 154l58.9 34M232.5 147l48.1 48.1M239.5 141.6l34 58.9M247.7 138.2l17.6 65.7"/></g></svg>',
    CN: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="75.24 0 342 342"><path fill="#D80027" d="M0 0h513v342H0z"/><g fill="#FFDA44"><path d="m226.8 239.2-9.7-15.6-17.9 4.4 11.9-14.1-9.7-15.6 17.1 6.9 11.8-14.1-1.3 18.4 17.1 6.9-17.9 4.4zM290.6 82l-10.1 15.4 11.6 14.3-17.7-4.8-10.1 15.5-1-18.4-17.7-4.8 17.2-6.6-1-18.4 11.6 14.3zM236.2 25.4l-2 18.3 16.8 7.6-18 3.8-2 18.3-9.2-16-17.9 3.8 12.3-13.7-9.2-15.9 16.8 7.5zM292.8 161.8l-14.9 10.9 5.8 17.5-14.9-10.8-14.9 11 5.6-17.6-14.9-10.7 18.4-.1 5.6-17.6 5.8 17.5zM115 46.3l17.3 53.5h56.2l-45.4 32.9 17.3 53.5-45.4-33-45.5 33 17.4-53.5-45.5-32.9h56.3z"/></g></svg>',
    KR: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 342 342"><path fill="#FFF" d="M0 0h342v342H0z"/><path d="m236.6 225.7 16.5-16.5 11 11-16.5 16.5-11-11zM209.1 253.3l16.5-16.5 11 11-16.5 16.5-11-11zM269.7 258.8l16.5-16.5 11 11-16.5 16.5-11-11zM242.1 286.4l16.5-16.5 11 11-16.5 16.5-11-11zM253.1 242.3l16.5-16.5 11 11-16.5 16.5-11-11zM225.6 269.9l16.5-16.5 11 11-16.5 16.5-11-11zM225.7 71.5l11-11 44.1 44.1-11 11-44.1-44.1zM209.1 88l11-11 16.5 16.5-11 11L209.1 88zM236.6 115.5l11-11 16.5 16.5-11 11-16.5-16.5zM242.1 54.9l11-11 16.5 16.5-11 11-16.5-16.5zM269.6 82.6l11-11 16.5 16.5-11 11-16.5-16.5zM43.8 253.4l11-11 44.1 44.1-11 11-44.1-44.1zM87.8 264.4l11-11 16.5 16.5-11 11-16.5-16.5zM60.3 236.7l11-11 16.5 16.5-11 11-16.5-16.5zM76.8 220.2l11-11 44.1 44.1-11 11-44.1-44.1zM43.8 88l44.1-44 11 11-44.1 44-11-11zM60.3 104.5l44.1-44.1 11 11-44.1 44.1-11-11zM76.8 121.1 120.9 77l11 11-44.1 44.1-11-11z"/><circle fill="#D80027" cx="170.3" cy="170.7" r="62.3"/><path fill="#0052B4" d="M232.2 178.3c-9.6-25.4-44.3-25-61.8 1.3-17.6 26.3-43.8 16.9-61.6.7 4.6 29.9 30.4 52.7 61.6 52.7 31.8 0 58-23.9 61.8-54.7z"/></svg>',
    TW: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="6.827 85.333 341.333 341.333"><path fill="#D80027" d="M0 85.337h512v341.326H0z"/><path fill="#0052B4" d="M0 85.337h256V256H0z"/><path fill="#FFF" d="M186.435 170.669 162.558 181.9l12.714 23.125-25.927-4.961-3.286 26.192L128 206.993l-18.06 19.263-3.285-26.192-25.927 4.96 12.714-23.125-23.877-11.23 23.877-11.231-12.714-23.125 25.927 4.96 3.286-26.192L128 134.344l18.06-19.263 3.285 26.192 25.928-4.96-12.715 23.125z"/><circle fill="#0052B4" cx="128" cy="170.674" r="29.006"/><path fill="#FFF" d="M128 190.06c-10.692 0-19.391-8.7-19.391-19.391 0-10.692 8.7-19.391 19.391-19.391 10.692 0 19.391 8.7 19.391 19.391 0 10.691-8.699 19.391-19.391 19.391z"/></svg>',
    BR: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#009b3a" d="M0 0h513v342H0z"/><path fill="#fedf00" d="m256.5 19.3 204.9 151.4L256.5 322 50.6 170.7z"/><circle fill="#FFF" cx="256.5" cy="171" r="80.4"/><path fill="#002776" d="M215.9 165.7c-13.9 0-27.4 2.1-40.1 6 .6 43.9 36.3 79.3 80.3 79.3 27.2 0 51.3-13.6 65.8-34.3-24.9-31-63.2-51-106-51zM334.9 186c.9-5 1.5-10.1 1.5-15.4 0-44.4-36-80.4-80.4-80.4-33.1 0-61.5 20.1-73.9 48.6 10.9-2.2 22.1-3.4 33.6-3.4 46.8.1 89 19.5 119.2 50.6z"/></svg>',
    ZA: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="35.84 85.333 341.333 341.333"><path fill="#FFF" d="M0 85.337h512v341.326H0z"/><path d="M114.024 256.001 0 141.926v228.17z"/><path fill="#ffb915" d="M161.192 256 0 94.7v47.226l114.024 114.075L0 370.096v47.138z"/><path fill="#007847" d="M509.833 289.391c.058-.44.804-.878 2.167-1.318v-65.464H222.602L85.33 85.337H0V94.7L161.192 256 0 417.234v9.429h85.33l137.272-137.272h287.231z"/><path fill="#000c8a" d="M503.181 322.783H236.433l-103.881 103.88H512v-103.88z"/><path fill="#e1392d" d="M503.181 189.217H512V85.337H132.552l103.881 103.88z"/></svg>',
    MX: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#dc2339" d="M342 0H0v341.3h513V0z"/><path fill="#11865d" d="M0 0h171v342H0z"/><path fill="#FFF" d="M171 0h171v342H171z"/><path fill="#8C9157" d="M195.8 171.2c0 21.6 11.5 41.7 30.3 52.5 5.8 3.4 13.2 1.4 16.6-4.4 3.4-5.8 1.4-13.2-4.4-16.6-11.3-6.5-18.2-18.5-18.2-31.5 0-6.7-5.4-12.1-12.1-12.1-6.7 0-12.2 5.4-12.2 12.1zm93.4 51.1c17.5-11.1 28-30.4 28-51.1 0-6.7-5.4-12.1-12.1-12.1s-12.1 5.4-12.1 12.1c0 12.4-6.3 24-16.8 30.7-5.7 3.5-7.5 10.9-4.1 16.7s10.9 7.5 16.7 4.1c0-.2.2-.3.4-.4z"/><ellipse fill="#C59262" cx="256.5" cy="159.1" rx="24.3" ry="36.4"/></svg>',
    EU: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 408 408"><path fill="#039" d="M0 0h408v408H0V0z"/><path fill="#FC0" d="m203.963 45.231 5.089 15.653h16.542l-13.322 9.68 5.015 15.67-13.323-9.68-13.323 9.68 5.089-15.662-13.322-9.68h16.468l5.087-15.661zm-68 18.134 5.089 15.653h16.542l-13.323 9.68 5.016 15.67-13.324-9.68-13.323 9.68 5.089-15.662-13.323-9.681h16.468l5.089-15.66zm-49.867 49.866 5.089 15.653h16.542l-13.323 9.68 5.016 15.67-13.324-9.68-13.323 9.68 5.089-15.662-13.323-9.68h16.468l5.089-15.661zM67.963 181.23l5.089 15.654h16.542l-13.323 9.682 5.016 15.67-13.324-9.682-13.323 9.682 5.089-15.664-13.323-9.679h16.468l5.089-15.663zm18.133 68.001 5.089 15.654h16.542l-13.323 9.68 5.016 15.67-13.324-9.68-13.323 9.68 5.089-15.662-13.323-9.68h16.468l5.089-15.662zm49.867 49.867 5.089 15.654h16.542l-13.323 9.68 5.016 15.67-13.324-9.679-13.323 9.679 5.089-15.661-13.323-9.681h16.468l5.089-15.662zm136-235.733 5.089 15.653h16.542l-13.322 9.68 5.015 15.67-13.323-9.68-13.324 9.68 5.09-15.662-13.322-9.681h16.468l5.087-15.66zm49.867 49.866 5.088 15.653h16.543l-13.323 9.68 5.015 15.67-13.322-9.68-13.324 9.68 5.09-15.662-13.323-9.68h16.468l5.088-15.661zm18.133 68 5.089 15.653h16.542l-13.322 9.682 5.015 15.67-13.323-9.682-13.323 9.682 5.089-15.664-13.322-9.679h16.468l5.087-15.662zm-18.133 68 5.088 15.654h16.543l-13.323 9.68 5.016 15.67-13.323-9.68-13.324 9.68 5.09-15.662-13.323-9.68h16.469l5.087-15.662zm-117.867 68 5.089 15.654h16.542l-13.322 9.68 5.015 15.67-13.323-9.68-13.323 9.68 5.089-15.662-13.322-9.68h16.468l5.087-15.662zm68-18.133 5.089 15.654h16.542l-13.322 9.68 5.016 15.67-13.324-9.68-13.322 9.68 5.088-15.662-13.322-9.68h16.469l5.086-15.662z"/></svg>',
    FR: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><path fill="#002654" d="M0 0h171v342H0z"/><path fill="#CE1126" d="M342 0h171v342H342z"/></svg>',
    DE: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#000" d="M0 0h513v114H0z"/><path fill="#DD0000" d="M0 114h513v114H0z"/><path fill="#FFCE00" d="M0 228h513v114H0z"/></svg>',
    IT: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><path fill="#009246" d="M0 0h171v342H0z"/><path fill="#CE2B37" d="M342 0h171v342H342z"/></svg>',
    NL: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><path fill="#AE1C28" d="M0 0h513v114H0z"/><path fill="#21468B" d="M0 228h513v114H0z"/></svg>',
    BE: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FDDA24" d="M0 0h513v342H0z"/><path fill="#000" d="M0 0h171v342H0z"/><path fill="#EF3340" d="M342 0h171v342H342z"/></svg>',
    IE: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><path fill="#169B62" d="M0 0h171v342H0z"/><path fill="#FF883E" d="M342 0h171v342H342z"/></svg>',
    AT: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><path fill="#C8102E" d="M0 0h513v114H0zM0 228h513v114H0z"/></svg>',
    ES: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="85.5 0 342 342"><path fill="#AA151B" d="M0 0h513v342H0z"/><path fill="#F1BF00" d="M0 85.5h513v171H0z"/></svg>',
    FI: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="23.94 0 342 342"><path fill="#FFF" d="M0 0h513v342H0z"/><path fill="#002F6C" d="M190 0h-60v140H0v60h130v142h60V200h323v-60H190z"/></svg>',
}
