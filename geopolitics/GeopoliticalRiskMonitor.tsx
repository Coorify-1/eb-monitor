import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

/**
 * GEOPOLITICAL RISK MONITOR — Economic Bearings
 * Same family as THE ANALYST and the Economic Calendar: flat beige page, serif titles
 * and numbers, thin rules. A dashboard with four tabs that switch in place:
 * Risk summary · Market movement · Calendar · Methodology.
 *
 * DATA
 *  - Data URL: eb-geopolitics.json, published every Monday by the EB engine (GitHub).
 *    Attention = news volume per risk (GDELT) against its usual level.
 *    Market reaction = do the 3 assets tied to each risk move the way the risk
 *    would move them (FRED, ECB, CoinGecko, our own pages)? Level comes with the
 *    data; you can set it per risk in Framer ("Risks"). The page only shows "Updated".
 *  - "Risks" (Framer list): add, remove or reorder risks. A risk the engine does not
 *    compute can still be shown by typing its attention and reaction by hand.
 *  - "Calendar events" (Framer list): major geopolitical dates, added to the engine's list.
 *  - With "Data URL" empty the component shows SAMPLE data (also on the Framer canvas
 *    until the first weekly update is published).
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

type Level = "high" | "medium" | "low"
type Asset = {
    name: string
    dir: number // +1 = the risk pushes this price up, -1 = down
    move?: number // 1-month move (% or bp)
    text?: string // "+14.0%"
    z?: number // move vs. its usual 1-month move
    page?: string
}
type Risk = {
    id: string
    label: string
    attention: number // 0 = usual level, 1 = well above usual
    attentionChange?: number // vs. last week
    reaction: number // −1 … +1
    levelAuto?: Level
    trend?: number[] // last 12 weeks of attention
    view?: string
    assets?: Asset[]
}
type CalEv = {
    date: string
    end?: string
    title: string
    region?: string
    risk?: string
    note?: string
}
type Data = {
    version?: number
    generated?: string
    updated?: string
    sample?: boolean
    week?: { year: number; number: number }
    nextUpdate?: string
    global?: {
        value: number
        change?: number
        series: [string, number][]
        events?: { date: string; label: string }[]
    }
    risks: Risk[]
    calendar?: CalEv[]
    sources?: string
}
type Row = Risk & {
    n: number
    level: Level
    adjusted: boolean
    manual: boolean
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

const isNum = (v: any): v is number => typeof v === "number" && isFinite(v)
const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))
const fam = (f: any, fallback: string) =>
    f && f.fontFamily
        ? '"' + String(f.fontFamily).replace(/"/g, "") + '",' + fallback
        : ""
const fmtDay = (
    iso: string | null | undefined,
    o: Intl.DateTimeFormatOptions
) => {
    if (!iso) return ""
    try {
        return new Date(
            iso.length <= 10 ? iso + "T12:00:00Z" : iso
        ).toLocaleDateString("en-GB", { timeZone: "UTC", ...o })
    } catch {
        return iso
    }
}
const sign = (v: number) => (v > 0 ? "+" : v < 0 ? "−" : "")
const f1 = (v: number) => sign(v) + Math.abs(v).toFixed(1)
const f2 = (v: number) => sign(v) + Math.abs(v).toFixed(2)
const todayKey = () => new Date().toISOString().slice(0, 10)
const dayMs = (k: string) => Date.parse(k.slice(0, 10) + "T12:00:00Z")
const daysBetween = (a: string, b: string) =>
    Math.round((dayMs(b) - dayMs(a)) / 864e5)

function isoWeek(iso?: string) {
    const d = iso ? new Date(iso) : new Date()
    const t = new Date(
        Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate())
    )
    const day = t.getUTCDay() || 7
    t.setUTCDate(t.getUTCDate() + 4 - day)
    const y0 = Date.UTC(t.getUTCFullYear(), 0, 1)
    return {
        year: t.getUTCFullYear(),
        number: Math.ceil(((+t - y0) / 864e5 + 1) / 7),
    }
}

/** Automatic level: attention and market reaction together. Same rule as the engine. */
function autoLevel(attention: number, reaction: number): Level {
    const s = 0.6 * attention + reaction
    return s >= 1 ? "high" : s >= 0.4 ? "medium" : "low"
}
const lvlVar = (l: Level) =>
    l === "high" ? "var(--hi)" : l === "medium" ? "var(--md)" : "var(--lo)"

/** asset status: moving with the risk, against it, or hardly moving */
function assetStatus(a: Asset): "with" | "against" | "flat" {
    const m = isNum(a.move) ? a.move : 0
    const big = isNum(a.z) ? Math.abs(a.z) >= 0.5 : Math.abs(m) >= 0.5
    if (!big || m === 0) return "flat"
    return Math.sign(m) === Math.sign(a.dir) ? "with" : "against"
}

const STORE = "egr:v1:"
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

function Panel({
    title,
    note,
    right,
    children,
}: {
    title: string
    note?: string
    right?: React.ReactNode
    children: React.ReactNode
}) {
    return (
        <section className="egr-panel">
            <header className="egr-ph">
                <div>
                    <h3>{title}</h3>
                    {note && <p className="egr-note">{note}</p>}
                </div>
                {right}
            </header>
            {children}
        </section>
    )
}

function Spark({ values, color }: { values: number[]; color: string }) {
    const w = 76
    const h = 24
    if (!values || values.length < 2) return <span className="egr-spark" />
    const lo = Math.min(...values)
    const hi = Math.max(...values)
    const sp = hi - lo || 1
    const x = (i: number) => (i / (values.length - 1)) * (w - 4) + 2
    const y = (v: number) => 3 + (1 - (v - lo) / sp) * (h - 6)
    const last = values[values.length - 1]
    return (
        <svg className="egr-spark" width={w} height={h} aria-hidden="true">
            <path
                d={values
                    .map(
                        (v, i) =>
                            (i ? "L" : "M") +
                            x(i).toFixed(1) +
                            "," +
                            y(v).toFixed(1)
                    )
                    .join("")}
                fill="none"
                stroke={color}
                strokeWidth={1.6}
                strokeLinejoin="round"
            />
            <circle cx={x(values.length - 1)} cy={y(last)} r={2.6} fill={color} />
        </svg>
    )
}

/* ------------------------------------------------------------------ */
/* Diagram 1 — Risk map: attention (up) vs. market reaction (right)     */
/* ------------------------------------------------------------------ */

function RiskMap({
    rows,
    sel,
    onSel,
    phone,
    height,
    tx,
}: {
    rows: Row[]
    sel: string | null
    onSel: (id: string) => void
    phone: boolean
    height: number
    tx: Record<string, string>
}) {
    const ref = React.useRef<HTMLDivElement>(null)
    const W = Math.max(260, useWidth(ref))
    const H = phone ? Math.round(clamp(W * 0.92, 260, 360)) : height
    const pl = phone ? 24 : 30
    const pr = phone ? 10 : 14
    const pt = 10
    const pb = phone ? 46 : 44
    const atts = rows.map((r) => r.attention)
    const yLo = Math.min(-0.6, Math.min(...atts, 0) - 0.4)
    const yHi = Math.max(2, Math.max(...atts, 0) + 0.6)
    const X = (v: number) => pl + ((clamp(v, -1, 1) + 1) / 2) * (W - pl - pr)
    const Y = (v: number) => pt + (1 - (v - yLo) / (yHi - yLo)) * (H - pt - pb)
    const R = phone ? 11 : 10

    // labels next to the dots (desktop / tablet), pushed apart so they never overlap
    const pts = rows.map((r) => ({
        r,
        x: X(r.reaction),
        y: Y(r.attention),
        ly: Y(r.attention),
        right: X(r.reaction) < W * 0.72,
    }))
    if (!phone) {
        const g = [...pts].sort((a, b) => a.y - b.y)
        for (let i = 1; i < g.length; i++)
            if (g[i].ly - g[i - 1].ly < 19) g[i].ly = g[i - 1].ly + 19
    }

    const x0 = X(0)
    const y0 = Y(0)
    return (
        <div ref={ref} className="egr-map">
            <svg
                width={W}
                height={H}
                role="img"
                aria-label={rows
                    .map(
                        (r) =>
                            `${r.label}: attention ${f1(r.attention)}, market reaction ${f2(r.reaction)}`
                    )
                    .join("; ")}
            >
                <rect
                    className="egr-q"
                    x={x0}
                    y={pt}
                    width={W - pr - x0}
                    height={y0 - pt}
                />
                <rect
                    className="egr-frame"
                    x={pl}
                    y={pt}
                    width={W - pl - pr}
                    height={H - pt - pb}
                />
                <line className="egr-zero" x1={x0} x2={x0} y1={pt} y2={H - pb} />
                <line className="egr-zero" x1={pl} x2={W - pr} y1={y0} y2={y0} />
                {!phone && (
                    <g className="egr-cap">
                        <text x={W - pr - 8} y={pt + 18} textAnchor="end">
                            {tx.qTR}
                        </text>
                        <text x={pl + 8} y={pt + 18}>
                            {tx.qTL}
                        </text>
                        <text x={W - pr - 8} y={H - pb - 10} textAnchor="end">
                            {tx.qBR}
                        </text>
                        <text x={pl + 8} y={H - pb - 10}>
                            {tx.qBL}
                        </text>
                    </g>
                )}
                {/* attention scale */}
                {[-3, -2, -1, 0, 1, 2, 3, 4].map((v) =>
                    v <= yHi && v >= yLo ? (
                        <text
                            key={v}
                            className="egr-axm"
                            x={pl - 7}
                            y={Y(v) + 4}
                            textAnchor="end"
                        >
                            {v}
                        </text>
                    ) : null
                )}
                <text
                    className="egr-ax"
                    transform={`translate(${pl - (phone ? 15 : 20)},${pt + (H - pt - pb) / 2}) rotate(-90)`}
                    textAnchor="middle"
                >
                    {tx.axisY} →
                </text>
                <text
                    className="egr-ax"
                    x={pl + (W - pl - pr) / 2}
                    y={H - (phone ? 22 : 18)}
                    textAnchor="middle"
                >
                    {tx.axisX}
                </text>
                <text className="egr-axm" x={pl} y={H - 4}>
                    ← {tx.against}
                </text>
                <text className="egr-axm" x={W - pr} y={H - 4} textAnchor="end">
                    {tx.withRisk} →
                </text>
                {/* dots */}
                {pts.map((p) => {
                    const on = sel === p.r.id
                    const lx = p.right ? p.x + R + 6 : p.x - R - 6
                    return (
                        <g
                            key={p.r.id}
                            className={"egr-dot" + (on ? " is-sel" : "")}
                            onClick={() => onSel(p.r.id)}
                            role="button"
                            aria-label={p.r.label}
                        >
                            {!phone && Math.abs(p.ly - p.y) > 3 && (
                                <line
                                    className="egr-lead"
                                    x1={p.right ? p.x + R : p.x - R}
                                    y1={p.y}
                                    x2={lx + (p.right ? -2 : 2)}
                                    y2={p.ly}
                                />
                            )}
                            <circle cx={p.x} cy={p.y} r={R + 8} fill="transparent" />
                            {on && <circle className="o" cx={p.x} cy={p.y} r={R + 4} />}
                            <circle
                                cx={p.x}
                                cy={p.y}
                                r={R}
                                fill={lvlVar(p.r.level)}
                            />
                            <text
                                className="egr-dn"
                                x={p.x}
                                y={p.y + 4}
                                textAnchor="middle"
                            >
                                {p.r.n}
                            </text>
                            {!phone && (
                                <text
                                    className={"egr-dl" + (on ? " is-on" : "")}
                                    x={lx}
                                    y={p.ly + 4.5}
                                    textAnchor={p.right ? "start" : "end"}
                                >
                                    {p.r.label}
                                </text>
                            )}
                        </g>
                    )
                })}
            </svg>
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Diagram 2 — Global attention over time                              */
/* ------------------------------------------------------------------ */

function AttentionChart({
    series,
    events,
    height,
    tx,
}: {
    series: [string, number][]
    events: { date: string; label: string }[]
    height: number
    tx: Record<string, string>
}) {
    const ref = React.useRef<HTMLDivElement>(null)
    const W = Math.max(260, useWidth(ref))
    const H = height
    const [range, setRange] = React.useState<"1y" | "5y" | "all">("all")
    const [hover, setHover] = React.useState<number | null>(null)
    const lastT = series.length ? dayMs(series[series.length - 1][0]) : 0
    const from =
        range === "all"
            ? -Infinity
            : lastT - (range === "1y" ? 1 : 5) * 365.25 * 864e5
    const pts = series.filter((p) => dayMs(p[0]) >= from)
    const n = pts.length
    const seg = (
        <div className="egr-seg" role="group">
            {(
                [
                    ["1y", tx.r1Y],
                    ["5y", tx.r5Y],
                    ["all", tx.rAll],
                ] as ["1y" | "5y" | "all", string][]
            ).map(([v, t]) => (
                <button
                    key={v}
                    type="button"
                    aria-pressed={range === v}
                    onClick={() => setRange(v)}
                >
                    {t}
                </button>
            ))}
        </div>
    )
    if (n < 2)
        return (
            <div ref={ref}>
                {seg}
                <div className="egr-empty" style={{ height: H }}>
                    {tx.chartLater}
                </div>
            </div>
        )
    const vals = pts.map((p) => p[1])
    let lo = Math.min(-0.5, ...vals)
    let hi = Math.max(1, ...vals)
    const sp = hi - lo
    lo -= sp * 0.08
    hi += sp * 0.12
    const step = [0.25, 0.5, 1].find((s) => (hi - lo) / s <= 5) || 1
    const ticks: number[] = []
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step)
        ticks.push(+v.toFixed(2))
    const pl = 4
    const pr = 40
    const pt = 12
    const pb = 26
    const x = (i: number) => pl + (i / (n - 1)) * (W - pl - pr)
    const y = (v: number) => pt + (1 - (v - lo) / (hi - lo)) * (H - pt - pb)

    // x labels: years, or quarters on the one-year view
    const xl: { i: number; t: string }[] = []
    for (let i = 1; i < n; i++) {
        const a = pts[i - 1][0]
        const b = pts[i][0]
        if (range === "1y") {
            if (a.slice(5, 7) !== b.slice(5, 7) && /^(01|04|07|10)$/.test(b.slice(5, 7)))
                xl.push({ i, t: fmtDay(b, { month: "short", year: "2-digit" }) })
        } else if (a.slice(0, 4) !== b.slice(0, 4)) xl.push({ i, t: b.slice(0, 4) })
    }
    const minGap = range === "all" && W < 520 ? 2 : 1
    const xlab = xl.filter((_, k) => k % minGap === 0)

    // events inside the range, numbered and pinned to the line
    const firstT = dayMs(pts[0][0])
    const evs = (events || [])
        .filter((e) => dayMs(e.date) >= firstT && dayMs(e.date) <= lastT + 7 * 864e5)
        .sort((a, b) => dayMs(a.date) - dayMs(b.date))
        .map((e, k) => {
            const t = dayMs(e.date)
            let best = 0
            for (let i = 1; i < n; i++)
                if (Math.abs(dayMs(pts[i][0]) - t) < Math.abs(dayMs(pts[best][0]) - t))
                    best = i
            return { ...e, k: k + 1, i: best }
        })

    const line = pts
        .map((p, i) => (i ? "L" : "M") + x(i).toFixed(1) + "," + y(p[1]).toFixed(1))
        .join("")
    const area = line + `L${x(n - 1).toFixed(1)},${y(0)}L${x(0).toFixed(1)},${y(0)}Z`
    const hEv =
        hover !== null ? evs.find((e) => Math.abs(e.i - hover) <= 2) : undefined

    return (
        <div className="egr-line">
            <div className="egr-linetop">{seg}</div>
            <div ref={ref} style={{ position: "relative" }}>
                <svg width={W} height={H} role="img" aria-label={tx.lineTitle}>
                    {ticks.map((v) => (
                        <g key={v}>
                            <line
                                x1={pl}
                                x2={W - pr + 4}
                                y1={y(v)}
                                y2={y(v)}
                                className={v === 0 ? "egr-zero" : "egr-gl"}
                            />
                            <text x={W - pr + 8} y={y(v) + 4} className="egr-axm">
                                {v === 0 ? "0" : f1(v).replace(".0", "")}
                            </text>
                        </g>
                    ))}
                    {xlab.map((l) => (
                        <text
                            key={l.i}
                            x={x(l.i)}
                            y={H - 6}
                            className="egr-axm"
                            textAnchor="middle"
                        >
                            {l.t}
                        </text>
                    ))}
                    <path d={area} className="egr-area" />
                    <path
                        d={line}
                        fill="none"
                        stroke="var(--link)"
                        strokeWidth={2}
                        strokeLinejoin="round"
                    />
                    {hover !== null && (
                        <line
                            x1={x(hover)}
                            x2={x(hover)}
                            y1={pt}
                            y2={H - pb}
                            className="egr-cross"
                        />
                    )}
                    {evs.map((e) => (
                        <g key={e.k} className="egr-evm">
                            <circle cx={x(e.i)} cy={y(pts[e.i][1])} r={9} />
                            <text
                                x={x(e.i)}
                                y={y(pts[e.i][1]) + 4}
                                textAnchor="middle"
                            >
                                {e.k}
                            </text>
                        </g>
                    ))}
                    <rect
                        x={pl}
                        y={pt}
                        width={W - pl - pr}
                        height={H - pt - pb}
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
                        className="egr-tip"
                        style={
                            x(hover) > W / 2
                                ? { right: W - x(hover) + 10 }
                                : { left: x(hover) + 10 }
                        }
                    >
                        <div className="egr-tip-d">
                            {fmtDay(pts[hover][0], {
                                day: "numeric",
                                month: "short",
                                year: "numeric",
                            })}
                        </div>
                        <div className="egr-tip-v">
                            {tx.attention} <b>{f2(pts[hover][1])}</b>
                        </div>
                        {hEv && <div className="egr-tip-e">{hEv.label}</div>}
                    </div>
                )}
            </div>
            {evs.length > 0 && (
                <ol className="egr-evl">
                    {evs.map((e) => (
                        <li key={e.k}>
                            <span className="egr-evn">{e.k}</span>
                            <span>
                                {e.label}
                                <small>
                                    {fmtDay(e.date, { month: "short", year: "numeric" })}
                                </small>
                            </span>
                        </li>
                    ))}
                </ol>
            )}
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Sample data (shown while "Data URL" is empty) — illustrative only    */
/* ------------------------------------------------------------------ */

function rng(seed: number) {
    return () => {
        seed |= 0
        seed = (seed + 0x6d2b79f5) | 0
        let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296
    }
}

const SAMPLE_EVENTS = [
    { date: "2018-03-01", label: "US steel and aluminium tariffs" },
    { date: "2020-01-03", label: "US–Iran Escalation" },
    { date: "2020-03-11", label: "COVID-19 Pandemic Declared" },
    { date: "2022-02-24", label: "Russia–Ukraine Conflict" },
    { date: "2023-10-07", label: "Israel–Hamas War" },
    { date: "2025-04-02", label: "US “reciprocal” tariffs" },
    { date: "2025-06-22", label: "Israel–Iran War" },
]

function buildSample(): Data {
    const r = rng(11)
    const g = () => {
        const u = Math.max(1e-9, r())
        return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r())
    }
    const bumps: [string, number][] = [
        ["2018-03-01", 0.6],
        ["2019-05-13", 0.45],
        ["2020-01-03", 0.75],
        ["2020-03-11", 0.7],
        ["2022-02-24", 1.7],
        ["2023-10-07", 1.05],
        ["2025-04-02", 1.15],
        ["2025-06-22", 1.1],
        ["2026-10-19", 0.95],
    ]
    const series: [string, number][] = []
    let x = 0
    for (let t = Date.UTC(2017, 0, 2); t <= Date.UTC(2026, 10, 16); t += 7 * 864e5) {
        x = 0.9 * x + 0.1 * g()
        let v = x - 0.2
        for (const [d, a] of bumps) {
            const k = (t - dayMs(d)) / (5 * 7 * 864e5)
            v += a * Math.exp(-k * k)
        }
        series.push([new Date(t).toISOString().slice(0, 10), +v.toFixed(3)])
    }
    const target = 0.86
    const end0 = series[series.length - 1][1]
    for (let k = 0; k < 10; k++) {
        const i = series.length - 10 + k
        series[i][1] = +(series[i][1] + ((target - end0) * (k + 1)) / 10).toFixed(3)
    }
    const last = series[series.length - 1][1]
    const prev = series[series.length - 2][1]

    const trend = (att: number, ch: number, seed: number) => {
        const q = rng(seed)
        const out: number[] = []
        for (let i = 0; i < 12; i++)
            out.push(att - ch - (10 - i) * 0.035 * Math.sign(ch || 1) + (q() - 0.5) * 0.18)
        out[10] = att - ch
        out[11] = att
        return out.map((v) => +v.toFixed(2))
    }
    const risk = (
        id: string,
        label: string,
        attention: number,
        ch: number,
        reaction: number,
        view: string,
        assets: Asset[]
    ): Risk => ({
        id,
        label,
        attention,
        attentionChange: ch,
        reaction,
        levelAuto: autoLevel(attention, reaction),
        trend: trend(attention, ch, id.length * 7),
        view,
        assets,
    })
    return {
        version: 1,
        sample: true,
        generated: "2026-11-16T11:00:00Z",
        week: { year: 2026, number: 47 },
        nextUpdate: "2026-11-23T11:00:00Z",
        global: {
            value: last,
            change: +(last - prev).toFixed(2),
            series,
            events: SAMPLE_EVENTS,
        },
        risks: [
            risk("middle_east", "Middle East conflict", 1.62, 0.18, 0.62,
                "The Gulf remains the most-watched risk. Oil and volatility are moving the way a wider conflict would move them.",
                [
                    { name: "Brent crude", dir: 1, move: 14.0, text: "+14.0%", z: 2.1, page: "energy" },
                    { name: "VIX volatility", dir: 1, move: 9.2, text: "+9.2%", z: 0.9, page: "markets" },
                    { name: "US high-yield bonds", dir: -1, move: -1.1, text: "−1.1%", z: 1.0, page: "markets" },
                ]),
            risk("energy", "Energy security", 1.08, 0.31, 0.48,
                "Supply workarounds are holding, but the system has little spare room. Gas prices and inflation expectations are drifting up.",
                [
                    { name: "US natural gas", dir: 1, move: 6.2, text: "+6.2%", z: 0.8, page: "energy" },
                    { name: "Energy stocks", dir: 1, move: 3.4, text: "+3.4%", z: 0.7, page: "markets" },
                    { name: "US 10-year inflation expectations", dir: 1, move: 12, text: "+12 bp", z: 1.1, page: "markets" },
                ]),
            risk("russia_nato", "Russia–NATO", 0.94, 0.52, 0.21,
                "Incidents below the threshold of open conflict are drawing more coverage. Markets are only partly pricing an escalation.",
                [
                    { name: "Brent crude", dir: 1, move: 14.0, text: "+14.0%", z: 2.1, page: "energy" },
                    { name: "Euro vs. dollar", dir: -1, move: 0.7, text: "+0.7%", z: 0.6, page: "crypto" },
                    { name: "European stocks", dir: -1, move: -0.3, text: "−0.3%", z: 0.1, page: "markets" },
                ]),
            risk("us_china", "US–China rivalry", 0.71, -0.08, 0.35,
                "Competition over chips and AI continues despite the trade truce. Asian currencies and chip stocks show some strain.",
                [
                    { name: "Chinese yuan", dir: -1, move: -0.4, text: "−0.4%", z: 0.6, page: "crypto" },
                    { name: "Taiwan dollar", dir: -1, move: -0.9, text: "−0.9%", z: 0.8, page: "crypto" },
                    { name: "US chip stocks", dir: -1, move: 2.1, text: "+2.1%", z: 0.5, page: "markets" },
                ]),
            risk("trade", "Trade & tariffs", 0.38, -0.21, -0.15,
                "Tariff headlines have faded from the front page. Currencies and consumer stocks are moving against a trade-war scenario.",
                [
                    { name: "Mexican peso", dir: -1, move: 1.2, text: "+1.2%", z: 0.7, page: "crypto" },
                    { name: "Copper", dir: -1, move: -0.6, text: "−0.6%", z: 0.3, page: "metals" },
                    { name: "US consumer stocks", dir: -1, move: 0.8, text: "+0.8%", z: 0.5, page: "markets" },
                ]),
            risk("cyber", "Cyber & terror attacks", 0.82, 0.12, 0.05,
                "Coverage of state-backed hacking is steady. Prices show little sign that a major incident is being priced.",
                [
                    { name: "VIX volatility", dir: 1, move: 9.2, text: "+9.2%", z: 0.9, page: "markets" },
                    { name: "Bitcoin", dir: -1, move: 1.5, text: "+1.5%", z: 0.6, page: "crypto" },
                    { name: "Global high-yield bonds", dir: -1, move: -0.2, text: "−0.2%", z: 0.2, page: "markets" },
                ]),
            risk("americas", "Western Hemisphere", 1.15, 0.06, 0.12,
                "US pressure across the region keeps the story in the news; the peso and regional bonds are calm.",
                [
                    { name: "Mexican peso", dir: -1, move: 1.2, text: "+1.2%", z: 0.7, page: "crypto" },
                    { name: "Gold", dir: 1, move: -5.2, text: "−5.2%", z: 1.4, page: "metals" },
                    { name: "Latin American bonds", dir: -1, move: -0.4, text: "−0.4%", z: 0.4, page: "markets" },
                ]),
            risk("korea", "North Korea", -0.21, -0.05, 0.08,
                "Missile tests draw brief bursts of attention; the won and the yen are steady.",
                [
                    { name: "Japanese yen", dir: 1, move: 0.7, text: "+0.7%", z: 0.6, page: "crypto" },
                    { name: "Korean won", dir: -1, move: 0.2, text: "+0.2%", z: 0.2, page: "crypto" },
                    { name: "Korean stocks", dir: -1, move: 1.0, text: "+1.0%", z: 0.4, page: "markets" },
                ]),
        ],
        calendar: [
            { date: "2026-11-29", title: "OPEC+ ministerial meeting on 2027 output", region: "Vienna (online)", risk: "energy" },
            { date: "2026-12-03", title: "NATO foreign ministers meet", region: "Brussels", risk: "russia_nato" },
            { date: "2026-12-14", end: "2026-12-15", title: "G20 leaders’ summit", region: "United States", risk: "trade" },
            { date: "2026-12-17", end: "2026-12-18", title: "European Council summit", region: "Brussels", risk: "russia_nato" },
            { date: "2027-01-10", title: "US–China trade truce expires", region: "US · China", risk: "us_china" },
            { date: "2027-02-12", end: "2027-02-14", title: "Munich Security Conference", region: "Germany", risk: "russia_nato" },
        ],
        sources:
            "Attention: the EB Geopolitical Attention Index tracks the relative frequency of news stories associated with each risk across global print, broadcast and online media in more than 60 languages (GDELT Project), scored against its five-year history. Market reaction: one-month moves in the three scenario assets tied to each risk, measured against their usual volatility. Market data: Federal Reserve Bank of St. Louis (FRED), COMEX and LME metal prices. Calendar: official calendars of governments and international institutions.",
    }
}
const SAMPLE = buildSample()

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
                    if (!alive || !j || !Array.isArray(j.risks)) throw 0
                    setData(j)
                    setStatus("ok")
                    writeStore("data:" + url, { at: Date.now(), json: j })
                })
                .catch(() => alive && setStatus(saved?.json ? "ok" : "error"))
        load()
        const id = setInterval(load, 6 * 3600 * 1000)
        return () => {
            alive = false
            clearInterval(id)
        }
    }, [url])
    return { data, status }
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

type TabId = "summary" | "market" | "calendar" | "method"

export default function GeopoliticalRiskMonitor(props: any) {
    const clean = (o: any): Record<string, any> =>
        Object.fromEntries(
            Object.entries(o || {}).filter(
                ([, v]) => v !== undefined && v !== null && v !== ""
            )
        )
    const p: any = { ...DEFAULTS, ...clean(props) }
    const keepEmpty = (o: any): Record<string, any> =>
        Object.fromEntries(
            Object.entries(o || {}).filter(([, v]) => v !== undefined && v !== null)
        )
    const tx: Record<string, string> = { ...DEF_TEXTS, ...keepEmpty(p.texts) }
    const links: Record<string, string> = { ...DEF_LINKS, ...clean(p.links) }
    const rootRef = React.useRef<HTMLDivElement>(null)
    const W = useWidth(rootRef)
    const phone = W < 600
    const wide = W >= 980
    const url = String(p.dataUrl || "").trim()
    const { data, status } = useData(url)
    const D: Data = data || SAMPLE
    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    // no update could be loaded: the live site says so instead of showing sample figures
    const missing = !data && status === "error" && !isCanvas
    const href = (k?: string) => (k && links[k] ? String(links[k]) : "")

    const [tab, setTab] = React.useState<TabId>(p.defaultTab || "summary")
    React.useEffect(() => setTab(p.defaultTab || "summary"), [p.defaultTab])
    const [sel, setSel] = React.useState<string | null>(null)

    /* ---------- risks: the Framer list decides which ones, in which order ---------- */
    const num = (v: any) => {
        const n = parseFloat(String(v ?? "").replace(",", ".").replace("−", "-"))
        return isFinite(n) ? n : null
    }
    const byId = new Map((D.risks || []).map((r) => [r.id, r]))
    const picks: any[] =
        Array.isArray(p.risks) && p.risks.length
            ? p.risks
            : (D.risks || []).map((r) => ({ id: r.id }))
    const rows: Row[] = (
        picks
            .filter((r) => r && r.show !== false)
            .map((r) => {
                const id = String(r.id || "").trim()
                const d: any = byId.get(id) || {}
                const ma = num(r.attention)
                const mr = num(r.reaction)
                const attention = ma ?? d.attention
                const reaction = mr ?? d.reaction
                if (!id || !isNum(attention) || !isNum(reaction)) return null
                const auto: Level =
                    ma !== null || mr !== null || !d.levelAuto
                        ? autoLevel(attention, reaction)
                        : d.levelAuto
                const ov: Level | null =
                    r.level && r.level !== "auto" ? (r.level as Level) : null
                return {
                    ...d,
                    id,
                    label: r.label || d.label || id,
                    attention,
                    reaction,
                    levelAuto: auto,
                    level: ov || auto,
                    adjusted: !!ov && ov !== auto,
                    view: r.view || d.view || "",
                    manual: !d.id,
                }
            })
            .filter(Boolean) as any[]
    ).map((r, i) => ({ ...r, n: i + 1 }))

    /* ---------- header figures ---------- */
    const wk = D.week || isoWeek(D.generated)
    const gVal = isNum(D.global?.value)
        ? D.global!.value
        : rows.reduce((a, r) => a + r.attention, 0) / Math.max(1, rows.length)
    const gCh = D.global?.change
    const nHigh = rows.filter((r) => r.level === "high").length
    const riser = rows
        .filter((r) => isNum(r.attentionChange))
        .sort((a, b) => (b.attentionChange || 0) - (a.attentionChange || 0))[0]
    const priced = [...rows].sort((a, b) => b.reaction - a.reaction)[0]
    const statusText =
        status === "sample" || (!data && isCanvas) ? tx.sample : missing ? tx.unavailable : tx.live

    /* ---------- tabs ---------- */
    const TABS: [TabId, string][] = [
        ["summary", phone ? tx.tabSummaryShort : tx.tabSummary],
        ["market", phone ? tx.tabMarketShort : tx.tabMarket],
        ["calendar", phone ? tx.tabCalendarShort : tx.tabCalendar],
        ["method", phone ? tx.tabMethodShort : tx.tabMethod],
    ]
    const shownTabs = TABS.filter(
        ([id]) =>
            (id !== "calendar" || p.showCalendar) && (id !== "method" || p.showMethod)
    )

    const lvlText = (l: Level) => tx["lvl_" + l] || l
    const attWord = (v: number) =>
        v >= 1.5
            ? tx.att_exceptional
            : v >= 0.6
              ? tx.att_wellAbove
              : v >= 0.2
                ? tx.att_above
                : v > -0.2
                  ? tx.att_usual
                  : v > -0.6
                    ? tx.att_below
                    : tx.att_quiet
    const reactWord = (v: number) =>
        v >= 0.4
            ? tx.re_pricing
            : v >= 0.15
              ? tx.re_partly
              : v > -0.15
                ? tx.re_little
                : tx.re_against

    /* ---------- tab 1: risk summary ---------- */
    const list = (
        <Panel title={tx.listTitle} note={tx.listNote}>
            <ol className="egr-list">
                {rows.map((r) => {
                    const open = sel === r.id
                    const w = clamp((Math.max(0, r.attention) / 2.5) * 100, 2, 100)
                    return (
                        <li
                            key={r.id}
                            className={"egr-row" + (open ? " is-open" : "")}
                        >
                            <button
                                type="button"
                                className="egr-rbtn"
                                aria-expanded={open}
                                onClick={() => setSel(open ? null : r.id)}
                            >
                                <span
                                    className="egr-num"
                                    style={{ background: lvlVar(r.level) }}
                                >
                                    {r.n}
                                </span>
                                <span className="egr-rname">{r.label}</span>
                                <span
                                    className="egr-lvl"
                                    style={{ color: lvlVar(r.level) }}
                                >
                                    {lvlText(r.level)}
                                </span>
                            </button>
                            <div className="egr-rmeta">
                                <span className="egr-meter" title={tx.attention}>
                                    <i style={{ width: w + "%" }} />
                                </span>
                                <span className="egr-rv" title={tx.attention + " " + f1(r.attention)}>
                                    {attWord(r.attention)}{" "}
                                    <small>{f1(r.attention)}</small>
                                    {isNum(r.attentionChange) &&
                                        Math.abs(r.attentionChange) >= 0.05 && (
                                            <span
                                                className={
                                                    r.attentionChange > 0
                                                        ? "egr-upw"
                                                        : "egr-dnw"
                                                }
                                            >
                                                {r.attentionChange > 0 ? " ▲" : " ▼"}
                                            </span>
                                        )}
                                </span>
                                {!phone && (
                                    <Spark
                                        values={r.trend || []}
                                        color={lvlVar(r.level)}
                                    />
                                )}
                            </div>
                            {open && (
                                <div className="egr-rdet">
                                    {r.view && <p>{r.view}</p>}
                                    <div className="egr-rnums">
                                        <span>
                                            {tx.attention} <b>{attWord(r.attention)}</b> ({f1(r.attention)})
                                        </span>
                                        <span>
                                            {tx.reaction} <b>{reactWord(r.reaction)}</b> ({f2(r.reaction)})
                                        </span>
                                    </div>
                                    {(r.assets || []).length > 0 && (
                                        <button
                                            type="button"
                                            className="egr-alink"
                                            onClick={() => setTab("market")}
                                        >
                                            {tx.seeAssets} →
                                        </button>
                                    )}
                                </div>
                            )}
                        </li>
                    )
                })}
            </ol>
        </Panel>
    )

    const map = (
        <Panel title={tx.mapTitle} note={tx.mapNote}>
            <RiskMap
                rows={rows}
                sel={sel}
                onSel={(id) => setSel(sel === id ? null : id)}
                phone={phone}
                height={p.mapHeight}
                tx={tx}
            />
            <div className="egr-legend">
                {(["high", "medium", "low"] as Level[]).map((l) => (
                    <span key={l}>
                        <i style={{ background: lvlVar(l) }} />
                        {lvlText(l)}
                    </span>
                ))}
            </div>
        </Panel>
    )

    const summary = (
        <div className={wide ? "egr-grid2" : "egr-col"}>
            {map}
            {list}
        </div>
    )

    /* ---------- tab 2: market movement ---------- */
    const lineChart = (
        <Panel title={tx.lineTitle} note={tx.lineNote}>
            <AttentionChart
                series={D.global?.series || []}
                events={D.global?.events || []}
                height={phone ? 210 : p.chartHeight}
                tx={tx}
            />
        </Panel>
    )

    const stText: Record<string, string> = {
        with: tx.st_with,
        against: tx.st_against,
        flat: tx.st_flat,
    }
    const scenario = (
        <Panel title={tx.scenTitle} note={tx.scenNote}>
            <div className="egr-sc">
                {!phone && (
                    <div className="egr-sch">
                        <span>{tx.colRisk}</span>
                        <span>{tx.reaction}</span>
                        <span>{tx.colAssets}</span>
                    </div>
                )}
                {rows.map((r) => {
                    const v = clamp(r.reaction, -1, 1)
                    return (
                        <div key={r.id} className="egr-scr">
                            <div className="egr-scn">
                                <span
                                    className="egr-num sm"
                                    style={{ background: lvlVar(r.level) }}
                                >
                                    {r.n}
                                </span>
                                <span>{r.label}</span>
                            </div>
                            <div className="egr-scb" title={f2(v)}>
                                <span className="egr-bar">
                                    <i
                                        style={{
                                            left: v >= 0 ? "50%" : 50 + v * 50 + "%",
                                            width: Math.abs(v) * 50 + "%",
                                            background:
                                                v >= 0 ? "var(--ink)" : "var(--mute)",
                                        }}
                                    />
                                </span>
                                <b>{f2(v)}</b>
                            </div>
                            <div className="egr-sca">
                                {(r.assets || []).map((a, k) => {
                                    const st = assetStatus(a)
                                    const u = href(a.page)
                                    const Tag: any = u ? "a" : "div"
                                    return (
                                        <Tag
                                            key={k}
                                            className={"egr-as is-" + st}
                                            {...(u
                                                ? { href: u, target: "_blank", rel: "noopener" }
                                                : {})}
                                            title={stText[st]}
                                        >
                                            <span className="egr-asn">{a.name}</span>
                                            <span className="egr-asv">
                                                <span className="egr-exp">
                                                    {a.dir > 0 ? "▲" : "▼"}
                                                </span>
                                                <b
                                                    className={
                                                        (a.move || 0) > 0
                                                            ? "egr-up"
                                                            : (a.move || 0) < 0
                                                              ? "egr-dn"
                                                              : ""
                                                    }
                                                >
                                                    {a.text ||
                                                        (isNum(a.move) ? f1(a.move) + "%" : "—")}
                                                </b>
                                                <i className="egr-st" aria-label={stText[st]} />
                                            </span>
                                        </Tag>
                                    )
                                })}
                            </div>
                        </div>
                    )
                })}
                <div className="egr-sck">
                    <span>
                        <span className="egr-exp">▲▼</span> {tx.expected}
                    </span>
                    <span>
                        <i className="egr-st is-with" /> {tx.st_with}
                    </span>
                    <span>
                        <i className="egr-st is-against" /> {tx.st_against}
                    </span>
                    <span>
                        <i className="egr-st is-flat" /> {tx.st_flat}
                    </span>
                </div>
            </div>
        </Panel>
    )
    const market = (
        <div className="egr-col">
            {lineChart}
            {scenario}
        </div>
    )

    /* ---------- tab 3: calendar (major geopolitical dates only) ---------- */
    const [calLimit, setCalLimit] = React.useState(6)
    const today = todayKey()
    const horizon = new Date(Date.now() + (Number(p.calendarMonths) || 6) * 30.5 * 864e5)
        .toISOString()
        .slice(0, 10)
    const manualCal: CalEv[] = (Array.isArray(p.calendarEvents) ? p.calendarEvents : [])
        .filter((e: any) => e && /^\d{4}-\d{2}-\d{2}$/.test(String(e.date || "").trim()) && e.title)
        .map((e: any) => ({
            date: String(e.date).trim(),
            end: /^\d{4}-\d{2}-\d{2}$/.test(String(e.end || "").trim())
                ? String(e.end).trim()
                : undefined,
            title: e.title,
            region: e.region || undefined,
            risk: e.risk || undefined,
            note: e.note || undefined,
        }))
    const seen = new Set<string>()
    const cal = [...manualCal, ...(p.useEngineCalendar ? D.calendar || [] : [])]
        .filter((e) => {
            const k = e.date + "|" + e.title.toLowerCase()
            if (seen.has(k)) return false
            seen.add(k)
            return (e.end || e.date) >= today && e.date <= horizon
        })
        .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    const rowOf = (id?: string) => rows.find((r) => r.id === id)
    const riskChip = (id?: string) => {
        const r = rowOf(id)
        if (!r) return null
        return (
            <button
                type="button"
                className="egr-rchip"
                onClick={() => {
                    setSel(r.id)
                    setTab("summary")
                }}
            >
                <i style={{ background: lvlVar(r.level) }} />
                {r.label}
            </button>
        )
    }
    const when = (e: CalEv) => {
        const d = Math.max(0, daysBetween(today, e.date))
        return e.date <= today
            ? e.end && e.end > today
                ? tx.calNow
                : tx.calToday
            : d === 1
              ? tx.calTomorrow
              : tx.calIn.replace("{n}", String(d))
    }
    const range = (e: CalEv) =>
        e.end && e.end !== e.date
            ? fmtDay(e.date, { day: "numeric" }) +
              "–" +
              fmtDay(e.end, { day: "numeric", month: "short" })
            : fmtDay(e.date, { day: "numeric", month: "short" })
    const next = cal[0]
    const rest = cal.slice(next ? 1 : 0)
    const calendar = (
        <div className={wide ? "egr-calgrid" : "egr-col"}>
            <Panel title={tx.calNext} note={tx.calNote}>
                {next ? (
                    <div className="egr-hero">
                        <div className="egr-hwd">
                            {fmtDay(next.date, { weekday: "long" })}
                        </div>
                        <div className="egr-hnum">
                            {+next.date.slice(8, 10)}
                            <span className="egr-slash" />
                        </div>
                        <div className="egr-hmo">
                            {fmtDay(next.date, { month: "long" })}{" "}
                            <span>{next.date.slice(0, 4)}</span>
                        </div>
                        <h4 className="egr-ht">{next.title}</h4>
                        <div className="egr-hmeta">
                            <b>{when(next)}</b>
                            {next.region && <span>{next.region}</span>}
                            {riskChip(next.risk)}
                        </div>
                        {next.note && <p className="egr-hnote">{next.note}</p>}
                    </div>
                ) : (
                    <p className="egr-empty2">{tx.calEmpty}</p>
                )}
            </Panel>
            <Panel title={tx.calTitle} note={tx.calRange.replace("{n}", String(Number(p.calendarMonths) || 6))}>
                {rest.length === 0 ? (
                    <p className="egr-empty2">{next ? tx.calOnly : tx.calEmpty}</p>
                ) : (
                    <ul className="egr-cal">
                        {rest.slice(0, calLimit).map((e, i) => (
                            <li key={e.date + i}>
                                <div className="egr-cd">
                                    <b>{range(e)}</b>
                                    <small>{when(e)}</small>
                                </div>
                                <div className="egr-cm">
                                    <span className="egr-ct">{e.title}</span>
                                    <span className="egr-cx">
                                        {e.region && <span>{e.region}</span>}
                                        {riskChip(e.risk)}
                                    </span>
                                    {e.note && <span className="egr-cn">{e.note}</span>}
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
                {rest.length > calLimit && (
                    <button
                        type="button"
                        className="egr-more"
                        onClick={() => setCalLimit((l) => l + 6)}
                    >
                        {tx.calMore.replace(
                            "{n}",
                            String(Math.min(6, rest.length - calLimit))
                        )}{" "}
                        ↓
                    </button>
                )}
                {href("calendar") && (
                    <a
                        className="egr-alink"
                        href={href("calendar")}
                        target="_blank"
                        rel="noopener"
                    >
                        {tx.calFull} →
                    </a>
                )}
            </Panel>
        </div>
    )

    /* ---------- tab 4: methodology ---------- */
    const method = (
        <div className={wide ? "egr-grid2" : "egr-col"}>
            <Panel title={tx.methodTitle}>
                <div className="egr-meth">
                    {[1, 2, 3, 4].map((i) => (
                        <div key={i}>
                            <h4>{tx["m" + i + "Title"]}</h4>
                            <p>{tx["m" + i]}</p>
                        </div>
                    ))}
                </div>
            </Panel>
            <Panel title={tx.readPanel}>
                <div className="egr-meth">
                    <div>
                        <h4>{tx.readTitle}</h4>
                        <p>{tx.read}</p>
                    </div>
                </div>
            </Panel>
        </div>
    )

    const body =
        tab === "summary"
            ? summary
            : tab === "market"
              ? market
              : tab === "calendar"
                ? calendar
                : method

    const vars = {
        "--bg": p.background,
        "--panel": p.panel,
        "--ink": p.ink,
        "--mute": p.muted,
        "--rule": p.rule,
        "--strong": p.strongRule,
        "--link": p.link,
        "--up": p.upColor,
        "--dn": p.downColor,
        "--hi": p.highColor,
        "--md": p.mediumColor,
        "--lo": p.lowColor,
        "--tab": p.tabColor,
        "--tabink": p.tabTextColor,
        "--maxw": Math.max(320, Number(p.maxWidth) || 1240) + "px",
        "--pad":
            (phone ? 16 : !wide ? Math.max(24, Number(p.padding) || 0) : Number(p.padding) || 0) +
            "px",
        "--minh": (phone ? 0 : Math.max(0, Number(p.minHeight) || 0)) + "px",
        "--t1": Math.max(18, Number(p.titleSize) || 30) + "px",
        "--t2": Math.max(15, Number(p.sectionTitleSize) || 20) + "px",
        "--kv": Math.max(18, Number(p.kpiSize) || 30) + "px",
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
            className={"egr" + (phone ? " egr-phone" : !wide ? " egr-mid" : "")}
            style={vars}
        >
            <style>{CSS}</style>
            <div className="egr-in">
                {p.showHeader && (
                    <header className="egr-mast">
                        <div>
                            {tx.kicker && <div className="egr-kick">{tx.kicker}</div>}
                            {tx.title && <h1>{tx.title}</h1>}
                            {tx.subtitle && <p className="egr-sub">{tx.subtitle}</p>}
                        </div>
                        <div className="egr-stamp">
                            <span
                                className={
                                    "egr-dot " +
                                    (status === "sample"
                                        ? "is-sample"
                                        : status === "ok"
                                          ? "is-live"
                                          : "")
                                }
                            />
                            <b>{statusText}</b>
                            <span className="egr-week">
                                {tx.week
                                    .replace("{w}", String(wk.number))
                                    .replace("{y}", String(wk.year))}
                            </span>
                            {(D.updated || D.generated) && (
                                <span>
                                    {tx.updated.replace(
                                        "{d}",
                                        fmtDay(D.updated || D.generated, { day: "numeric", month: "short" })
                                    )}
                                </span>
                            )}
                            {D.nextUpdate && (
                                <span>
                                    {tx.nextUpdate.replace(
                                        "{d}",
                                        fmtDay(D.nextUpdate, {
                                            weekday: "short",
                                            day: "numeric",
                                            month: "short",
                                        })
                                    )}
                                </span>
                            )}
                        </div>
                    </header>
                )}

                {missing ? (
                    <p className="egr-missing">{tx.missing}</p>
                ) : (
                    <>
                        {p.showKpis && (
                            <div className="egr-kpis">
                                <div className="egr-kpi">
                                    <div className="egr-kl">{tx.kpiGlobal}</div>
                                    <div className="egr-kv">{f2(gVal)}</div>
                                    <div className="egr-ks">
                                        {isNum(gCh) && Math.abs(gCh) >= 0.01 && (
                                            <span className={gCh > 0 ? "egr-upw" : "egr-dnw"}>
                                                {gCh > 0 ? "▲ " : "▼ "}
                                                {Math.abs(gCh).toFixed(2)}{" "}
                                            </span>
                                        )}
                                        <span className="egr-mut">{tx.kpiGlobalNote}</span>
                                    </div>
                                </div>
                                <div className="egr-kpi">
                                    <div className="egr-kl">{tx.kpiHigh}</div>
                                    <div className="egr-kv">
                                        {nHigh}
                                        <span className="egr-kof"> / {rows.length}</span>
                                    </div>
                                    <div className="egr-ks egr-mut">{tx.kpiHighNote}</div>
                                </div>
                                {riser && (
                                    <button
                                        type="button"
                                        className="egr-kpi"
                                        onClick={() => {
                                            setSel(riser.id)
                                            setTab("summary")
                                        }}
                                    >
                                        <div className="egr-kl">{tx.kpiRiser}</div>
                                        <div className="egr-kv egr-kt">{riser.label}</div>
                                        <div className="egr-ks">
                                            <span className="egr-upw">
                                                ▲ {Math.abs(riser.attentionChange || 0).toFixed(2)}
                                            </span>{" "}
                                            <span className="egr-mut">{tx.kpiRiserNote}</span>
                                        </div>
                                    </button>
                                )}
                                {priced && (
                                    <button
                                        type="button"
                                        className="egr-kpi"
                                        onClick={() => setTab("market")}
                                    >
                                        <div className="egr-kl">{tx.kpiPriced}</div>
                                        <div className="egr-kv egr-kt">{priced.label}</div>
                                        <div className="egr-ks">
                                            <b>{f2(priced.reaction)}</b>{" "}
                                            <span className="egr-mut">{tx.kpiPricedNote}</span>
                                        </div>
                                    </button>
                                )}
                            </div>
                        )}

                        <div className="egr-tabs" role="tablist">
                            {shownTabs.map(([id, t]) => (
                                <button
                                    key={id}
                                    type="button"
                                    role="tab"
                                    className="egr-tab"
                                    aria-selected={tab === id}
                                    onClick={() => setTab(id)}
                                >
                                    {t}
                                </button>
                            ))}
                        </div>

                        <div className="egr-body" role="tabpanel" key={tab}>
                            {body}
                        </div>
                    </>
                )}

                {p.showFooter && (
                    <footer className="egr-foot">
                        <p>
                            <b>{tx.footBold}</b> {tx.footText}
                        </p>
                        <details>
                            <summary>{tx.sourcesTitle}</summary>
                            <p>{D.sources || SAMPLE.sources}</p>
                        </details>
                    </footer>
                )}
            </div>
        </div>
    )
}

/* ------------------------------------------------------------------ */
/* Styles (same system as THE ANALYST)                                  */
/* ------------------------------------------------------------------ */

const CSS = `
.egr{width:100%;background:var(--bg);color:var(--ink);font-family:var(--fb);font-size:14px;line-height:1.45;box-sizing:border-box;padding:var(--pad);-webkit-font-smoothing:antialiased}
.egr *{box-sizing:border-box}
.egr button{font-family:var(--fb);color:inherit}
.egr a{color:inherit;text-decoration:none}
.egr-in{max-width:var(--maxw);margin:0 auto;display:flex;flex-direction:column;gap:20px}
.egr-up{color:var(--up)} .egr-dn{color:var(--dn)} .egr-mut{color:var(--mute)}
.egr-upw{color:var(--hi)} .egr-dnw{color:var(--mute)}
/* masthead */
.egr-mast{display:flex;justify-content:space-between;align-items:flex-end;gap:10px 24px;flex-wrap:wrap;border-bottom:1px solid var(--rule);padding-bottom:14px}
.egr-kick{font-size:12px;font-weight:500;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin-bottom:6px}
.egr-mast h1{font-family:var(--fh);font-weight:400;font-size:var(--t1);line-height:1.12;margin:0;letter-spacing:.04em}
.egr-sub{margin:6px 0 0;color:var(--mute);font-size:14px;line-height:1.5;max-width:640px}
.egr-stamp{display:flex;align-items:center;flex-wrap:wrap;gap:4px 12px;font-size:13px;color:var(--mute)}
.egr-stamp b{color:var(--ink);font-weight:600}
.egr-week{font-family:var(--fh);font-size:15px;color:var(--ink)}
.egr-dot{width:7px;height:7px;border-radius:50%;display:inline-block;background:var(--mute)}
.egr-dot.is-live{background:var(--up);animation:egr-blink 1.8s ease-in-out infinite}
.egr-dot.is-sample{background:#C98B00}
@keyframes egr-blink{0%,100%{opacity:1}50%{opacity:.3}}
/* key figures */
.egr-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-top:1px solid var(--strong);border-bottom:1px solid var(--rule)}
.egr .egr-kpi{appearance:none;border:0;background:none;text-align:left;font:inherit;box-shadow:inset -1px 0 0 var(--rule);padding:14px 18px;display:flex;flex-direction:column;gap:4px;min-width:0}
.egr button.egr-kpi{cursor:pointer}
.egr button.egr-kpi:hover .egr-kl{color:var(--link)}
.egr-kpi:first-child{padding-left:0}
.egr-kpi:last-child{box-shadow:none}
.egr-kl{font-size:12px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;color:var(--mute)}
.egr-kv{font-family:var(--fh);font-size:var(--kv);line-height:1.12;font-variant-numeric:tabular-nums lining-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.egr-kv.egr-kt{font-size:calc(var(--kv) * .72);line-height:1.25;padding:3px 0 2px}
.egr-kof{font-size:.6em;color:var(--mute)}
.egr-ks{font-size:13px;font-variant-numeric:tabular-nums}
/* tabs */
.egr-tabs{display:flex;gap:2px;border-bottom:2px solid var(--tab);margin-bottom:-4px;overflow-x:auto;scrollbar-width:none}
.egr-tabs::-webkit-scrollbar{display:none}
.egr .egr-tab{appearance:none;border:0;background:none;padding:12px 24px 11px;font-size:15px;font-weight:500;color:var(--ink);cursor:pointer;border-radius:5px 5px 0 0;white-space:nowrap;flex:none;transition:background .15s,color .15s}
.egr .egr-tab:hover{background:color-mix(in srgb,var(--tab) 8%,transparent)}
.egr .egr-tab[aria-selected="true"]{background:var(--tab);color:var(--tabink);font-weight:600}
.egr-body{min-height:var(--minh);animation:egr-in .22s ease-out}
@keyframes egr-in{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.egr-body,.egr-dot.is-live{animation:none}}
.egr-grid2{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:24px 44px;align-items:start}
.egr-col{display:flex;flex-direction:column;gap:28px;min-width:0}
.egr-body{padding-top:6px}
.egr-body>.egr-grid2>.egr-panel,.egr-body>.egr-calgrid>.egr-panel,.egr-body>.egr-col>.egr-panel:first-child{border-top:0}
/* panels */
.egr-panel{border-top:1px solid var(--strong);min-width:0}
.egr-ph{display:flex;justify-content:space-between;align-items:flex-start;gap:8px 16px;flex-wrap:wrap;padding:12px 0 12px}
.egr-ph h3{margin:0;font-family:var(--fh);font-weight:400;font-size:var(--t2);line-height:1.2}
.egr-note{margin:3px 0 0;font-size:13px;color:var(--mute);line-height:1.45}
.egr-empty{display:flex;align-items:center;justify-content:center;color:var(--mute);font-size:14px}
.egr-empty2{color:var(--mute);font-size:15px;margin:8px 0}
/* risk map */
.egr-map svg{display:block;overflow:visible}
.egr .egr-q{fill:color-mix(in srgb,var(--hi) 5%,transparent)}
.egr .egr-frame{stroke:var(--rule);fill:none}
.egr .egr-zero{stroke:var(--strong);stroke-width:1;stroke-dasharray:3 3}
.egr .egr-gl{stroke:var(--rule);stroke-width:1}
.egr .egr-cap text{fill:var(--mute);font-size:12.5px;font-family:var(--fb);font-style:italic}
.egr .egr-ax{fill:var(--ink);font-size:12.5px;font-weight:600;font-family:var(--fb)}
.egr .egr-axm{fill:var(--mute);font-size:12px;font-family:var(--fb);font-variant-numeric:tabular-nums}
.egr .egr-dl{fill:var(--ink);font-size:14px;font-family:var(--fh)}
.egr .egr-dl.is-on{font-weight:700}
.egr .egr-dn{fill:#fff;font-size:12px;font-weight:700;font-family:var(--fb);pointer-events:none}
.egr .egr-lead{stroke:var(--mute);stroke-width:.8}
.egr-dot{cursor:pointer}
.egr-dot circle.o{fill:none;stroke:var(--ink);stroke-width:1.5}
.egr-dot:hover text.egr-dl{fill:var(--link)}
.egr-legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:13px;padding-top:10px}
.egr-legend span{display:inline-flex;align-items:center;gap:7px}
.egr-legend i{width:10px;height:10px;border-radius:50%;display:inline-block}
/* risk list */
.egr-list{list-style:none;margin:0;padding:0}
.egr-row{border-top:1px solid var(--rule);padding:10px 0 11px}
.egr-row:first-child{border-top:0;padding-top:2px}
.egr .egr-rbtn{appearance:none;border:0;background:none;padding:0;width:100%;display:grid;grid-template-columns:26px minmax(0,1fr) auto;gap:12px;align-items:center;text-align:left;cursor:pointer}
.egr-num{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;color:#fff;font-size:12px;font-weight:700;flex:none}
.egr-num.sm{width:22px;height:22px;font-size:11.5px}
.egr-rname{font-family:var(--fh);font-size:17px;line-height:1.25}
.egr-rbtn:hover .egr-rname{color:var(--link)}
.egr-lvl{font-size:12px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;white-space:nowrap}
.egr-lvl em{font-style:normal;color:var(--mute);letter-spacing:0}
.egr-rmeta{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:14px;align-items:center;padding:6px 0 0 38px}
.egr-meter{position:relative;height:8px}
.egr-meter::before{content:"";position:absolute;left:0;right:0;top:3.5px;height:1px;background:var(--rule)}
.egr-meter i{position:absolute;left:0;top:3.5px;height:1px;background:var(--ink)}
.egr-meter i::after{content:"";position:absolute;right:-3px;top:-2.5px;width:6px;height:6px;border-radius:50%;background:var(--ink)}
.egr-rv{font-family:var(--fh);font-size:15px;font-variant-numeric:tabular-nums;white-space:nowrap}
.egr-rv small{font-family:var(--fb);font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums}
.egr-spark{display:block;width:76px;height:24px}
.egr-rdet{padding:10px 0 2px 38px;animation:egr-in .2s ease-out}
.egr-rdet p{margin:0 0 8px;font-family:var(--fh);font-size:16px;line-height:1.55}
.egr-rnums{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:13px;color:var(--mute)}
.egr-rnums b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
.egr .egr-alink{appearance:none;border:0;background:none;padding:0;margin-top:8px;display:inline-block;font-size:14px;color:var(--link);cursor:pointer;border-bottom:1px solid color-mix(in srgb,var(--link) 35%,transparent)}
/* line chart */
.egr-line svg{display:block;overflow:visible}
.egr-linetop{display:flex;justify-content:flex-end;margin:-46px 0 14px;min-height:32px}
.egr .egr-area{fill:color-mix(in srgb,var(--link) 9%,transparent)}
.egr .egr-cross{stroke:var(--mute);stroke-width:1}
.egr-evm circle{fill:var(--bg);stroke:var(--ink);stroke-width:1.2}
.egr-evm text{fill:var(--ink);font-size:11.5px;font-weight:700;font-family:var(--fb);pointer-events:none}
.egr-seg{display:inline-flex;border:1px solid var(--rule);border-radius:7px;padding:2px;background:var(--panel)}
.egr .egr-seg button{appearance:none;border:0;background:none;padding:5px 13px;border-radius:5px;font-size:13px;color:var(--mute);cursor:pointer}
.egr .egr-seg button[aria-pressed="true"]{background:var(--ink);color:var(--bg);font-weight:600}
.egr-tip{position:absolute;top:6px;background:var(--bg);border:1px solid var(--rule);border-top:2px solid var(--ink);padding:8px 10px;font-size:13px;pointer-events:none;min-width:170px;max-width:240px;z-index:3}
.egr-tip-d{font-weight:600;margin-bottom:2px}
.egr-tip-v{color:var(--mute)} .egr-tip-v b{color:var(--ink);font-variant-numeric:tabular-nums}
.egr-tip-e{margin-top:4px;font-family:var(--fh);font-size:14px}
.egr-evl{list-style:none;margin:14px 0 0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:8px 24px}
.egr-evl li{display:flex;gap:10px;align-items:baseline;font-size:14px;line-height:1.35}
.egr-evl small{display:block;font-size:12.5px;color:var(--mute)}
.egr-evn{flex:none;display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;border-radius:50%;border:1.2px solid var(--ink);font-size:11.5px;font-weight:700;transform:translateY(3px)}
/* scenario check */
.egr-sc{display:flex;flex-direction:column}
.egr-sch,.egr-scr{display:grid;grid-template-columns:minmax(170px,.9fr) 170px minmax(0,2.6fr);gap:20px;align-items:center}
.egr-sch{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);padding-bottom:8px;border-bottom:1px solid var(--rule)}
.egr-scr{padding:12px 0;border-bottom:1px solid var(--rule)}
.egr-scn{display:flex;align-items:center;gap:10px;font-family:var(--fh);font-size:16px;line-height:1.25}
.egr-scb{display:flex;align-items:center;gap:10px}
.egr-scb b{font-family:var(--fh);font-weight:400;font-size:15px;font-variant-numeric:tabular-nums;width:42px;text-align:right}
.egr-bar{position:relative;flex:1;height:12px}
.egr-bar::before{content:"";position:absolute;left:0;right:0;top:5.5px;height:1px;background:var(--rule)}
.egr-bar::after{content:"";position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--strong)}
.egr-bar i{position:absolute;top:2px;height:8px}
.egr-sca{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.egr-as{display:flex;flex-direction:column;gap:3px;padding:8px 10px;border:1px solid var(--rule);border-radius:6px;background:var(--panel);min-width:0}
a.egr-as:hover{border-color:var(--strong)}
.egr-asn{font-size:13.5px;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.egr-asv{display:flex;align-items:center;gap:8px;font-family:var(--fh);font-size:15px;font-variant-numeric:tabular-nums}
.egr-asv b{font-weight:400}
.egr-exp{font-family:var(--fb);font-size:11px;color:var(--mute)}
.egr-st{margin-left:auto;width:10px;height:10px;border-radius:50%;display:inline-block;flex:none}
.egr-as.is-with .egr-st,.egr-st.is-with{background:var(--ink)}
.egr-as.is-against .egr-st,.egr-st.is-against{background:transparent;box-shadow:inset 0 0 0 1.5px var(--ink)}
.egr-as.is-flat .egr-st,.egr-st.is-flat{background:var(--rule)}
.egr-as.is-with{border-color:color-mix(in srgb,var(--ink) 35%,var(--rule))}
.egr-sck{display:flex;flex-wrap:wrap;gap:6px 20px;font-size:13px;color:var(--mute);padding-top:12px}
.egr-sck span{display:inline-flex;align-items:center;gap:7px}
.egr-sck .egr-st{margin:0}
/* calendar */
.egr-calgrid{display:grid;grid-template-columns:minmax(260px,.8fr) minmax(0,1.6fr);gap:24px 48px;align-items:start}
.egr-hero{padding:4px 0 8px}
.egr-hwd{font-family:var(--fh);font-size:19px;color:var(--mute)}
.egr-hnum{display:flex;align-items:flex-start;font-family:var(--fh);font-size:120px;line-height:.86;letter-spacing:-.04em;margin:12px 0 14px}
.egr-slash{display:inline-block;width:6px;height:.9em;margin-left:.1em;background:var(--hi);transform:skewX(-18deg);transform-origin:bottom}
.egr-hmo{font-family:var(--fh);font-size:24px} .egr-hmo span{color:var(--mute)}
.egr-ht{font-family:var(--fh);font-weight:400;font-size:24px;line-height:1.2;margin:18px 0 10px;padding-top:16px;border-top:1px solid var(--rule)}
.egr-hmeta{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;font-size:14px;color:var(--mute)}
.egr-hmeta b{color:var(--hi);font-weight:600}
.egr-hnote{font-size:15px;line-height:1.5;margin:10px 0 0}
.egr .egr-rchip{appearance:none;display:inline-flex;align-items:center;gap:7px;height:28px;padding:0 11px;border:1px solid var(--rule);border-radius:999px;background:var(--panel);font-size:13px;color:var(--ink);cursor:pointer}
.egr .egr-rchip:hover{border-color:var(--strong)}
.egr-rchip i{width:8px;height:8px;border-radius:50%;display:inline-block}
.egr-cal{list-style:none;margin:0;padding:0}
.egr-cal li{display:grid;grid-template-columns:120px minmax(0,1fr);gap:18px;padding:14px 0;border-top:1px solid var(--rule)}
.egr-cal li:first-child{border-top:0;padding-top:4px}
.egr-cd b{display:block;font-family:var(--fh);font-weight:400;font-size:20px;line-height:1.15}
.egr-cd small{font-size:13px;color:var(--mute)}
.egr-cm{display:flex;flex-direction:column;gap:7px;min-width:0}
.egr-ct{font-family:var(--fh);font-size:18px;line-height:1.3}
.egr-cx{display:flex;flex-wrap:wrap;align-items:center;gap:6px 12px;font-size:14px;color:var(--mute)}
.egr-cn{font-size:14px;line-height:1.5}
.egr .egr-more{appearance:none;display:block;width:100%;margin-top:6px;padding:12px 0;border:0;border-top:1px solid var(--rule);background:none;font-size:14px;color:var(--ink);cursor:pointer;text-align:center}
.egr .egr-more:hover{color:var(--link)}
/* methodology */
.egr-meth{display:flex;flex-direction:column;gap:16px}
.egr-meth h4{margin:0 0 4px;font-family:var(--fh);font-weight:400;font-size:18px}
.egr-meth p{margin:0;font-size:15px;line-height:1.6}
.egr-disc{color:var(--mute)} .egr-disc b{color:var(--ink)}
.egr-missing{font-family:var(--fh);font-size:18px;color:var(--mute);padding:40px 0;margin:0}
/* footer */
.egr-foot{border-top:1px solid var(--rule);padding-top:10px;font-size:13px;line-height:1.55;color:var(--mute)}
.egr-foot p{margin:0}
.egr-foot b{color:var(--ink);font-weight:600}
.egr-foot summary{cursor:pointer;color:var(--link);margin:6px 0 4px}
.egr-foot details p{margin:0 0 4px}
/* tablet */
.egr-mid .egr-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
.egr-mid .egr-kpi:nth-child(2){box-shadow:none}
.egr-mid .egr-kpi:nth-child(3){padding-left:0}
.egr-mid .egr-kpi:nth-child(n+3){border-top:1px solid var(--rule)}
.egr-mid .egr-rname{font-size:18px}
.egr-mid .egr-rdet p{font-size:17px}
.egr-mid .egr-sch,.egr-mid .egr-scr{grid-template-columns:minmax(150px,1fr) 160px;row-gap:10px}
.egr-mid .egr-sch span:last-child{display:none}
.egr-mid .egr-sca{grid-column:1/-1}
/* phone */
.egr-phone .egr-mast h1{font-size:calc(var(--t1) * .8)}
.egr-phone .egr-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
.egr-phone .egr-kpi{padding:12px 10px 12px 0}
.egr-phone .egr-kpi:nth-child(2n){padding-left:12px;box-shadow:none}
.egr-phone .egr-kpi:nth-child(n+3){border-top:1px solid var(--rule)}
.egr-phone .egr-kv{font-size:calc(var(--kv) * .85)}
.egr-phone .egr-kv.egr-kt{font-size:17px}
.egr-phone .egr-tabs{margin:0 -16px -4px;padding:0 16px}
.egr-phone .egr-tab{padding:11px 14px 10px;font-size:14.5px}
.egr-phone .egr-rmeta{grid-template-columns:minmax(0,1fr) auto}
.egr-phone .egr-rname{font-size:17px}
.egr-phone .egr-linetop{margin:0 0 10px;justify-content:flex-start}
.egr-phone .egr-evl{grid-template-columns:minmax(0,1fr)}
.egr-phone .egr-scr{grid-template-columns:minmax(0,1fr);gap:10px}
.egr-phone .egr-sca{grid-template-columns:minmax(0,1fr)}
.egr-phone .egr-as{flex-direction:row;align-items:center;justify-content:space-between;gap:10px;padding:7px 10px}
.egr-phone .egr-sca{gap:6px}
.egr-phone .egr-asn{font-size:14px}
.egr-phone .egr-hnum{font-size:88px}
.egr-phone .egr-cal li{grid-template-columns:minmax(0,1fr);gap:6px}
.egr-phone .egr-cd{display:flex;align-items:baseline;gap:10px}
`

/* ------------------------------------------------------------------ */
/* Texts, links, defaults and Framer controls                           */
/* ------------------------------------------------------------------ */

const DEF_LINKS: Record<string, string> = {
    markets: "/market-data",
    energy: "/energy-terminal",
    crypto: "/crypto-currencies",
    metals: "/hard-assets-terminal",
    calendar: "/economic-calendar",
    analyst: "/the-analyst",
}

const DEF_TEXTS: Record<string, string> = {
    kicker: "Economic Bearings",
    title: "GEOPOLITICAL RISK MONITOR",
    subtitle:
        "The geopolitical risks that matter for markets: how much the world is talking about them, and whether prices are moving. Updated every Monday.",
    live: "This week",
    sample: "Sample data",
    unavailable: "Update unavailable",
    missing: "This week's update is not available yet. Please check back shortly.",
    week: "Week {w} · {y}",
    updated: "Updated {d}",
    nextUpdate: "Next update {d}",
    tabSummary: "Risk summary",
    tabMarket: "Market movement",
    tabCalendar: "Calendar",
    tabMethod: "Methodology",
    tabSummaryShort: "Summary",
    tabMarketShort: "Markets",
    tabCalendarShort: "Calendar",
    tabMethodShort: "Method",
    kpiGlobal: "Global attention",
    kpiGlobalNote: "vs. last week · 0 = usual",
    kpiHigh: "Risks rated high",
    kpiHighNote: "of the risks we follow",
    kpiRiser: "Biggest riser",
    kpiRiserNote: "attention this week",
    kpiPriced: "Most priced in",
    kpiPricedNote: "market reaction",
    mapTitle: "Risk map",
    mapNote: "Attention against market reaction. Tap a dot for our view.",
    axisX: "Market reaction",
    axisY: "Attention",
    against: "Against the risk",
    withRisk: "With the risk",
    qTR: "Watched and priced",
    qTL: "Watched, not priced",
    qBR: "Priced quietly",
    qBL: "Off the radar",
    listTitle: "The risks we follow",
    listNote: "Level, then news attention against its five-year norm, with the last 12 weeks",
    attention: "Attention",
    att_exceptional: "Exceptional",
    att_wellAbove: "Well above usual",
    att_above: "Above usual",
    att_usual: "Usual",
    att_below: "Below usual",
    att_quiet: "Quiet",
    re_pricing: "Pricing the risk",
    re_partly: "Partly pricing it",
    re_little: "Little sign",
    re_against: "Moving against it",
    reaction: "Market reaction",
    seeAssets: "See the assets we watch",
    lvl_high: "High",
    lvl_medium: "Medium",
    lvl_low: "Low",
    lineTitle: "Global attention over time",
    lineNote: "Average of all risks, weekly. 0 = usual level, 1 = well above.",
    chartLater: "The chart appears with the next update.",
    r1Y: "1Y",
    r5Y: "5Y",
    rAll: "All",
    scenTitle: "Is the market pricing it?",
    scenNote:
        "For each risk, three assets: the direction they would take if the risk happened (▲▼), and their actual move over one month.",
    colRisk: "Risk",
    colAssets: "Assets we watch · 1-month move",
    expected: "Expected if the risk happens",
    st_with: "Moving with the risk",
    st_against: "Moving against",
    st_flat: "Little change",
    calNext: "Next big date",
    calNote: "Major geopolitical events only",
    calTitle: "Coming up",
    calRange: "The next {n} months",
    calIn: "In {n} days",
    calToday: "Today",
    calNow: "Under way",
    calTomorrow: "Tomorrow",
    calEmpty: "No major event scheduled.",
    calOnly: "Nothing else scheduled yet.",
    calMore: "Show {n} more",
    calFull: "Full economic calendar",
    methodTitle: "How the monitor works",
    m1Title: "Attention",
    m1: "Each week we measure the share of world news coverage that matches each risk (GDELT, more than 60 languages), averaged over two weeks, and compare it with the same measure over the previous five years. 0 = usual coverage, +1 = one standard deviation above, +2 or more = exceptional.",
    m2Title: "Market reaction",
    m2: "Each risk has three assets that would move clearly if it happened. For each, we take the one-month change up to the previous Sunday and divide it by its typical one-month change over the past two years. Moves in the expected direction count for, moves the other way count against, up to twice the typical size. +1 = all three move fully as if the risk were happening; −1 = all three move fully the opposite way.",
    m3Title: "Level",
    m3: "High, Medium or Low is the structural level of each risk, reviewed every month against official and press sources. It is raised for the week when news attention and market reaction are both strongly elevated; it is never lowered by quiet markets alone.",
    m4Title: "Weekly update",
    m4: "The monitor is updated every Monday morning with the previous week's data. The calendar lists only the major geopolitical dates we expect to matter for markets.",
    sourcesTitle: "Sources",
    readPanel: "Reading the monitor",
    readTitle: "How to read the risk map",
    read: "Higher on the map means more news attention. Further right means prices are already moving the way the risk would move them. Top right: the risk is watched and priced. Top left: watched, but markets are not reacting yet.",
    footBold: "For information only, not investment advice.",
    footText:
        "Scenarios are illustrative and do not cover every outcome. Past moves do not predict future returns.",
}

const DEF_RISKS = [
    { id: "middle_east", label: "", level: "auto", view: "", show: true },
    { id: "energy", label: "", level: "auto", view: "", show: true },
    { id: "russia_nato", label: "", level: "auto", view: "", show: true },
    { id: "us_china", label: "", level: "auto", view: "", show: true },
    { id: "trade", label: "", level: "auto", view: "", show: true },
    { id: "cyber", label: "", level: "auto", view: "", show: true },
]

const DEFAULTS: Record<string, any> = {
    dataUrl:
        "https://raw.githubusercontent.com/Coorify-1/eb-monitor/main/docs/eb-geopolitics.json",
    risks: DEF_RISKS,
    calendarEvents: [],
    useEngineCalendar: true,
    calendarMonths: 6,
    defaultTab: "summary",
    showHeader: true,
    showKpis: true,
    showCalendar: true,
    showMethod: true,
    showFooter: true,
    mapHeight: 430,
    chartHeight: 280,
    minHeight: 620,
    maxWidth: 1240,
    padding: 24,
    titleSize: 30,
    sectionTitleSize: 20,
    kpiSize: 30,
    background: "#F0E6DC",
    panel: "#F7F0E9",
    ink: "#1A1A1A",
    muted: "#7A736C",
    rule: "#D9CFC4",
    strongRule: "#57514B",
    link: "#0D7680",
    upColor: "#1A8F3C",
    downColor: "#D0021B",
    highColor: "#990F3D",
    mediumColor: "#C08A1E",
    lowColor: "#9A9189",
    tabColor: "#1A1A1A",
    tabTextColor: "#F0E6DC",
    links: DEF_LINKS,
    texts: DEF_TEXTS,
}

GeopoliticalRiskMonitor.defaultProps = DEFAULTS

const CONTROLS: Record<string, any> = {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        placeholder: "https://raw.githubusercontent.com/…/eb-geopolitics.json",
        description: "Updated every Monday. Empty = sample data.",
    },
    risks: {
        type: ControlType.Array,
        title: "Risks",
        description:
            "Add, remove or drag to reorder. ID = the engine's risk (middle_east, energy, russia_nato, us_china, trade, cyber, americas, korea…). For a new risk the engine does not compute yet, type its attention and reaction.",
        control: {
            type: ControlType.Object,
            controls: {
                id: { type: ControlType.String, title: "ID", placeholder: "middle_east" },
                show: { type: ControlType.Boolean, title: "Show", defaultValue: true },
                label: { type: ControlType.String, title: "Name", placeholder: "Auto" },
                level: {
                    type: ControlType.Enum,
                    title: "Level",
                    options: ["auto", "high", "medium", "low"],
                    optionTitles: ["Auto", "High", "Medium", "Low"],
                    defaultValue: "auto",
                },
                view: {
                    type: ControlType.String,
                    title: "Our view",
                    displayTextArea: true,
                    placeholder: "Empty = the engine's text",
                },
                attention: {
                    type: ControlType.String,
                    title: "Attention",
                    placeholder: "Empty = engine (e.g. 1.2)",
                },
                reaction: {
                    type: ControlType.String,
                    title: "Reaction",
                    placeholder: "Empty = engine (−1 to 1)",
                },
            },
        },
    },
    calendarEvents: {
        type: ControlType.Array,
        title: "Calendar events",
        description: "Major geopolitical dates only. Added to the engine's list.",
        control: {
            type: ControlType.Object,
            controls: {
                date: { type: ControlType.String, title: "Date", placeholder: "2026-12-14" },
                end: { type: ControlType.String, title: "End", placeholder: "Optional" },
                title: { type: ControlType.String, title: "Event", placeholder: "G20 leaders' summit" },
                region: { type: ControlType.String, title: "Where", placeholder: "United States" },
                risk: { type: ControlType.String, title: "Risk ID", placeholder: "trade" },
                note: { type: ControlType.String, title: "Note", displayTextArea: true },
            },
        },
    },
    useEngineCalendar: { type: ControlType.Boolean, title: "Engine dates" },
    calendarMonths: {
        type: ControlType.Number,
        title: "Months ahead",
        min: 1,
        max: 24,
        step: 1,
    },
    defaultTab: {
        type: ControlType.Enum,
        title: "Opening tab",
        options: ["summary", "market", "calendar", "method"],
        optionTitles: ["Risk summary", "Market movement", "Calendar", "Methodology"],
    },
    links: {
        type: ControlType.Object,
        title: "Page links",
        controls: Object.fromEntries(
            Object.keys(DEF_LINKS).map((k) => [
                k,
                { type: ControlType.String, title: k, defaultValue: DEF_LINKS[k] },
            ])
        ),
    },
    showHeader: { type: ControlType.Boolean, title: "Header" },
    showKpis: { type: ControlType.Boolean, title: "Key figures" },
    showCalendar: { type: ControlType.Boolean, title: "Calendar tab" },
    showMethod: { type: ControlType.Boolean, title: "Method tab" },
    showFooter: { type: ControlType.Boolean, title: "Footer" },
    minHeight: {
        type: ControlType.Number,
        title: "Tab height",
        min: 0,
        max: 1200,
        step: 10,
        unit: "px",
        description: "Minimum height of the tab area, so the page does not jump when switching tabs (desktop and tablet).",
    },
    mapHeight: { type: ControlType.Number, title: "Map height", min: 280, max: 640, step: 10, unit: "px" },
    chartHeight: { type: ControlType.Number, title: "Chart height", min: 180, max: 480, step: 10, unit: "px" },
    maxWidth: { type: ControlType.Number, title: "Max width", min: 320, max: 1800, step: 10, unit: "px" },
    padding: { type: ControlType.Number, title: "Padding", min: 0, max: 120, unit: "px" },
    titleSize: { type: ControlType.Number, title: "Title size", min: 18, max: 64 },
    sectionTitleSize: { type: ControlType.Number, title: "Section size", min: 15, max: 40 },
    kpiSize: { type: ControlType.Number, title: "Key figure size", min: 18, max: 56 },
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
    panel: { type: ControlType.Color, title: "Cards" },
    ink: { type: ControlType.Color, title: "Text" },
    muted: { type: ControlType.Color, title: "Muted" },
    rule: { type: ControlType.Color, title: "Row lines" },
    strongRule: { type: ControlType.Color, title: "Header lines" },
    link: { type: ControlType.Color, title: "Links / chart line" },
    upColor: { type: ControlType.Color, title: "Price up" },
    downColor: { type: ControlType.Color, title: "Price down" },
    highColor: { type: ControlType.Color, title: "Level high" },
    mediumColor: { type: ControlType.Color, title: "Level medium" },
    lowColor: { type: ControlType.Color, title: "Level low" },
    tabColor: { type: ControlType.Color, title: "Active tab" },
    tabTextColor: { type: ControlType.Color, title: "Active tab text" },
    texts: {
        type: ControlType.Object,
        title: "Texts",
        description: "Edit any text. Empty a field to hide that text.",
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
addPropertyControls(GeopoliticalRiskMonitor, CONTROLS)
