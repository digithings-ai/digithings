"use client"

/**
 * Waterfall — two shapes (no equivalent existed in finance-charts /
 * finance-tearsheet / metrics / finance-composites):
 *
 *   - `WaterfallBridge`: cumulative bridge of signed steps (attribution).
 *     Steps of kind `total` anchor to zero. Sign colours are P&L (up/down)
 *     by default; pass `signTone="neutral"` for non-money bridges (accent
 *     for positive, warn for negative).
 *   - `WaterfallTrace`: call-trace rows by `start` + `duration`. Status is
 *     health, so it uses accent / warn / ink-mute, never up/down.
 *
 * SVG only, presentational.
 */
import * as React from "react"

import { cn } from "../lib/utils"

export type WaterfallStep = {
  id?: string
  label: string
  value: number
  /** `total` bars start at 0 and show `value` as the running total. */
  kind?: "delta" | "total"
}

export type WaterfallBridgeProps = {
  steps: WaterfallStep[]
  signTone?: "pnl" | "neutral"
  formatValue?: (n: number) => string
  onSelect?: (index: number) => void
  label?: string
  emptyLabel?: string
  className?: string
}

export type WaterfallTraceRow = {
  id: string
  label: string
  /** Offset from trace origin (same unit as duration). */
  start: number
  duration: number
  status?: "ok" | "warn" | "mute"
  /** Nesting depth for indentation. */
  depth?: number
}

export type WaterfallTraceProps = {
  rows: WaterfallTraceRow[]
  /** Total span; defaults to the max row end. */
  total?: number
  formatDuration?: (n: number) => string
  selectedId?: string | null
  onSelect?: (id: string) => void
  label?: string
  emptyLabel?: string
  className?: string
}

const SIGN = {
  pnl: { pos: "fill-up", neg: "fill-down" },
  neutral: { pos: "fill-accent", neg: "fill-warn" },
} as const
const TRACE_STATUS = {
  ok: "fill-accent",
  warn: "fill-warn",
  mute: "fill-ink-mute",
} as const

function Empty({ text, className }: { text: string; className?: string }) {
  return (
    <div
      data-slot="waterfall"
      data-empty=""
      className={cn(
        "flex min-h-32 items-center justify-center font-mono text-xs text-ink-mute",
        className,
      )}
    >
      {text}
    </div>
  )
}

function activate(fn: () => void) {
  return (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      fn()
    }
  }
}

export function WaterfallBridge({
  steps,
  signTone = "pnl",
  formatValue = (n) => `${n > 0 ? "+" : ""}${Math.round(n * 100) / 100}`,
  onSelect,
  label = "Waterfall bridge",
  emptyLabel = "No steps to show.",
  className,
}: WaterfallBridgeProps) {
  const valid = steps.filter((s) => Number.isFinite(s.value))
  if (!valid.length) return <Empty text={emptyLabel} className={className} />

  let run = 0
  const bars = valid.map((s) => {
    const total = s.kind === "total"
    const from = total ? 0 : run
    const to = total ? s.value : run + s.value
    run = to
    return { s, total, lo: Math.min(from, to), hi: Math.max(from, to), end: to }
  })
  const min = Math.min(0, ...bars.map((b) => b.lo))
  const max = Math.max(0, ...bars.map((b) => b.hi))
  const span = max - min || 1

  const W = 640
  const H = 260
  const pad = { t: 16, r: 8, b: 40, l: 8 }
  const iw = W - pad.l - pad.r
  const ih = H - pad.t - pad.b
  const slot = iw / bars.length
  const bw = Math.min(56, slot * 0.6)
  const y = (v: number) => pad.t + ih - ((v - min) / span) * ih
  const summary = valid
    .map((s) => `${s.label} ${s.kind === "total" ? "total " : ""}${formatValue(s.value)}`)
    .join(", ")

  return (
    <figure data-slot="waterfall" data-variant="bridge" className={cn("m-0", className)}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={label}
        className="block h-auto w-full font-mono"
      >
        <line
          x1={pad.l}
          x2={W - pad.r}
          y1={y(0)}
          y2={y(0)}
          className="stroke-hair"
          strokeWidth={1}
        />
        {bars.map((b, i) => {
          const cx = pad.l + slot * i + slot / 2
          const cls = b.total
            ? "fill-ink-soft"
            : b.s.value >= 0
              ? SIGN[signTone].pos
              : SIGN[signTone].neg
          const prev = bars[i - 1]
          const bar = (
            <>
              <rect
                x={cx - bw / 2}
                y={y(b.hi)}
                width={bw}
                height={Math.max(1, y(b.lo) - y(b.hi))}
                className={cls}
              />
              <text x={cx} y={y(b.hi) - 4} textAnchor="middle" className="fill-ink" fontSize={10}>
                {formatValue(b.s.value)}
              </text>
              <text x={cx} y={H - 22} textAnchor="middle" className="fill-ink-soft" fontSize={10}>
                {b.s.label}
              </text>
            </>
          )
          return (
            <g key={b.s.id ?? `${b.s.label}-${i}`} data-slot="waterfall-step">
              {prev ? (
                <line
                  x1={cx - slot + bw / 2}
                  x2={cx - bw / 2}
                  y1={y(prev.end)}
                  y2={y(prev.end)}
                  className="stroke-ink-mute"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                />
              ) : null}
              {onSelect ? (
                <g
                  role="button"
                  tabIndex={0}
                  aria-label={`${b.s.label} ${formatValue(b.s.value)}`}
                  className="cursor-pointer focus-visible:outline-none"
                  onClick={() => onSelect(i)}
                  onKeyDown={activate(() => onSelect(i))}
                >
                  {bar}
                </g>
              ) : (
                bar
              )}
            </g>
          )
        })}
      </svg>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  )
}

export function WaterfallTrace({
  rows,
  total,
  formatDuration = (n) => `${Math.round(n * 100) / 100}`,
  selectedId,
  onSelect,
  label = "Call trace waterfall",
  emptyLabel = "No spans to show.",
  className,
}: WaterfallTraceProps) {
  const valid = rows.filter((r) => Number.isFinite(r.start) && Number.isFinite(r.duration))
  if (!valid.length) return <Empty text={emptyLabel} className={className} />

  const span =
    Math.max(total ?? 0, ...valid.map((r) => r.start + Math.max(0, r.duration))) || 1
  const W = 640
  const rowH = 22
  const labelW = 180
  const pad = { t: 4, r: 56, b: 4 }
  const H = pad.t + pad.b + valid.length * rowH
  const iw = W - labelW - pad.r
  const summary = valid
    .map((r) => `${r.label} starts ${formatDuration(r.start)} for ${formatDuration(r.duration)}`)
    .join("; ")

  return (
    <figure data-slot="waterfall" data-variant="trace" className={cn("m-0", className)}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={label}
        className="block h-auto w-full font-mono"
      >
        {valid.map((r, i) => {
          const y0 = pad.t + i * rowH
          const x0 = labelW + (r.start / span) * iw
          const bw = Math.max(2, (Math.max(0, r.duration) / span) * iw)
          const selected = r.id === selectedId
          const row = (
            <>
              <rect
                x={0}
                y={y0}
                width={W}
                height={rowH}
                className={selected ? "fill-accent-weak" : "fill-transparent"}
              />
              <line
                x1={0}
                x2={W}
                y1={y0 + rowH}
                y2={y0 + rowH}
                className="stroke-hair"
                strokeWidth={1}
              />
              <text
                x={8 + (r.depth ?? 0) * 12}
                y={y0 + rowH / 2}
                dominantBaseline="middle"
                className="fill-ink-soft"
                fontSize={10}
              >
                {r.label}
              </text>
              <rect
                x={x0}
                y={y0 + 5}
                width={bw}
                height={rowH - 10}
                className={TRACE_STATUS[r.status ?? "ok"]}
              />
              <text
                x={W - pad.r + 6}
                y={y0 + rowH / 2}
                dominantBaseline="middle"
                className="fill-ink-mute"
                fontSize={10}
              >
                {formatDuration(r.duration)}
              </text>
            </>
          )
          return onSelect ? (
            <g
              key={r.id}
              data-slot="waterfall-row"
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              aria-label={`${r.label} ${formatDuration(r.duration)}`}
              className="cursor-pointer focus-visible:outline-none"
              onClick={() => onSelect(r.id)}
              onKeyDown={activate(() => onSelect(r.id))}
            >
              {row}
            </g>
          ) : (
            <g key={r.id} data-slot="waterfall-row">
              {row}
            </g>
          )
        })}
      </svg>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  )
}
