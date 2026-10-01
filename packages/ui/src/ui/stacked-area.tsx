"use client"

/**
 * StackedAreaChart — time x weights, stacked. Replaces the recharts sleeve
 * chart in apps/dashboard (components/portfolio/sleeve-stacked-chart.tsx);
 * no equivalent existed in finance-charts / finance-tearsheet / metrics.
 *
 * SVG only (SSR-safe), presentational: rows in, `onSelect(x)` out. Series
 * colour comes from an ordered list of kit token classes (never raw hex);
 * the optional cash series is drawn last in a neutral ink-mute wash so it
 * never competes with a sleeve hue.
 */
import * as React from "react"

import { cn } from "../lib/utils"

/** Ordered token fills; cycled by series index. Literal strings so Tailwind sees them. */
export const STACKED_AREA_PALETTE = [
  "fill-accent/70",
  "fill-ink/60",
  "fill-warn/70",
  "fill-ink-soft/60",
  "fill-accent/40",
  "fill-ink/30",
  "fill-warn/40",
  "fill-ink-soft/30",
] as const

export type StackedAreaRow = Record<string, number | string | null | undefined>

export type StackedAreaChartProps = {
  data: StackedAreaRow[]
  /** Series keys, bottom to top. */
  keys: string[]
  /** Row field holding the x label (ISO date). Default `date`. */
  xKey?: string
  /** Optional cash series key, stacked on top in a neutral wash. */
  cashKey?: string
  formatKey?: (key: string) => string
  /** Y value formatter for axis + summary. Default `${n}%`. */
  formatValue?: (n: number) => string
  /** Fixed y max (default 100 — weights in percent). Pass `null` to fit the data. */
  yMax?: number | null
  /** Highlighted x (must equal a row's xKey value). */
  selectedX?: string | null
  /** Fired with the row's x when a column is clicked / activated. */
  onSelect?: (x: string) => void
  /** Accessible name; a numeric summary is appended in an sr-only caption. */
  label?: string
  emptyLabel?: string
  className?: string
}

const W = 640
const H = 280
const PAD = { t: 8, r: 8, b: 20, l: 36 }

function num(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v)
  return Number.isFinite(n) && n > 0 ? n : 0
}

export function StackedAreaChart({
  data,
  keys,
  xKey = "date",
  cashKey,
  formatKey = (k) => k,
  formatValue = (n) => `${Math.round(n)}%`,
  yMax = 100,
  selectedX,
  onSelect,
  label = "Stacked area chart",
  emptyLabel = "Not enough history to chart.",
  className,
}: StackedAreaChartProps) {
  const series = cashKey && !keys.includes(cashKey) ? [...keys, cashKey] : keys
  if (!data.length || !series.length) {
    return (
      <div
        data-slot="stacked-area"
        data-empty=""
        className={cn(
          "flex min-h-40 items-center justify-center font-mono text-xs text-ink-mute",
          className,
        )}
      >
        {emptyLabel}
      </div>
    )
  }

  const n = data.length
  const totals = data.map((r) => series.reduce((s, k) => s + num(r[k]), 0))
  const top = yMax ?? Math.max(1, ...totals)
  const iw = W - PAD.l - PAD.r
  const ih = H - PAD.t - PAD.b
  const x = (i: number) => PAD.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw)
  const y = (v: number) => PAD.t + ih - (Math.min(v, top) / top) * ih

  const bands = series.map((k, si) => {
    const upper = data.map((r) =>
      series.slice(0, si + 1).reduce((s, kk) => s + num(r[kk]), 0),
    )
    const lower = data.map((r) =>
      series.slice(0, si).reduce((s, kk) => s + num(r[kk]), 0),
    )
    const pts = (arr: number[]) => arr.map((v, i) => `${x(i)},${y(v)}`)
    const d =
      n === 1
        ? `M${x(0) - 3},${y(upper[0])} L${x(0) + 3},${y(upper[0])} L${x(0) + 3},${y(lower[0])} L${x(0) - 3},${y(lower[0])} Z`
        : `M${pts(upper).join(" L")} L${pts(lower).reverse().join(" L")} Z`
    return { k, d, isCash: k === cashKey }
  })

  const xs = data.map((r) => String(r[xKey] ?? ""))
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top)
  const xTickIdx = Array.from(new Set([0, Math.floor((n - 1) / 2), n - 1]))
  const colW = n === 1 ? iw : iw / (n - 1)
  const selIdx = selectedX != null ? xs.indexOf(selectedX) : -1
  const last = data[n - 1]
  const summary = `${xs[0]} to ${xs[n - 1]}. Latest: ${series
    .map((k) => `${formatKey(k)} ${formatValue(num(last[k]))}`)
    .join(", ")}.`

  return (
    <figure data-slot="stacked-area" className={cn("m-0", className)}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={label}
        className="block h-auto w-full font-mono"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD.l}
              x2={W - PAD.r}
              y1={y(t)}
              y2={y(t)}
              className="stroke-hair"
              strokeWidth={1}
            />
            <text
              x={PAD.l - 4}
              y={y(t)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-ink-mute"
              fontSize={9}
            >
              {formatValue(t)}
            </text>
          </g>
        ))}
        {bands.map((b, i) => (
          <path
            key={b.k}
            d={b.d}
            data-series={b.k}
            className={cn(
              b.isCash
                ? "fill-ink-mute/25"
                : STACKED_AREA_PALETTE[i % STACKED_AREA_PALETTE.length],
              "stroke-surface",
            )}
            strokeWidth={0.5}
          />
        ))}
        {xTickIdx.map((i, j) => (
          <text
            key={i}
            x={x(i)}
            y={H - 6}
            textAnchor={j === 0 ? "start" : i === n - 1 ? "end" : "middle"}
            className="fill-ink-mute"
            fontSize={9}
          >
            {xs[i]}
          </text>
        ))}
        {selIdx >= 0 ? (
          <line
            data-slot="stacked-area-selected"
            x1={x(selIdx)}
            x2={x(selIdx)}
            y1={PAD.t}
            y2={PAD.t + ih}
            className="stroke-accent"
            strokeWidth={1}
            strokeDasharray="4 4"
          />
        ) : null}
        {onSelect
          ? xs.map((xv, i) => (
              <rect
                key={xv + i}
                data-slot="stacked-area-hit"
                x={x(i) - colW / 2}
                y={PAD.t}
                width={colW}
                height={ih}
                className="cursor-pointer fill-transparent hover:fill-accent/10 focus-visible:fill-accent/10 focus-visible:outline-none"
                role="button"
                tabIndex={i === 0 || i === selIdx ? 0 : -1}
                aria-label={`Select ${xv}`}
                aria-pressed={i === selIdx}
                onClick={() => onSelect(xv)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    onSelect(xv)
                  }
                }}
              />
            ))
          : null}
      </svg>
      <figcaption className="sr-only">{summary}</figcaption>
      <ul
        data-slot="stacked-area-legend"
        className="m-0 mt-2 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 font-mono text-[11px] text-ink-soft"
      >
        {bands.map((b, i) => (
          <li key={b.k} className="flex items-center gap-1.5">
            <svg width={10} height={10} aria-hidden="true">
              <rect
                width={10}
                height={10}
                className={
                  b.isCash
                    ? "fill-ink-mute/25"
                    : STACKED_AREA_PALETTE[i % STACKED_AREA_PALETTE.length]
                }
              />
            </svg>
            {formatKey(b.k)}
          </li>
        ))}
      </ul>
    </figure>
  )
}
