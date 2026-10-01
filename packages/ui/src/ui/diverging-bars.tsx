/**
 * DivergingBars + ScoreBar — signed magnitude bars on a zero-centred track.
 *
 * Promotes the app-local `ConsensusScoreBar` (`.dbar-*` CSS in apps/dashboard)
 * into the kit as SVG parts: no canvas, SSR-safe, presentational (data via
 * props). Tracks are `preserveAspectRatio="none"` SVGs in a 0..100 x-space with
 * `vector-effect: non-scaling-stroke` ticks, so they size to any container.
 *
 *   - `DivergingBars` — ranked horizontal signed bars with a label and a value.
 *   - `ScoreBar`      — one bar with reference ticks and an optional target
 *                       marker (the ConsensusScoreBar recipe, generalised).
 *
 * Tone: `signed` colours by direction with up/down (P&L semantics); `accent`
 * uses the accent for both directions; per-item `tone` overrides. Health-style
 * values should pass `accent` / `warn` / `mute`, never up/down.
 */
import * as React from "react"
import { cva } from "class-variance-authority"

import { cn } from "../lib/utils"

export type BarTone = "up" | "down" | "accent" | "warn" | "mute"

const fillVariants = cva("", {
  variants: {
    tone: {
      up: "fill-up",
      down: "fill-down",
      accent: "fill-accent",
      warn: "fill-warn",
      mute: "fill-ink-mute",
    },
  },
  defaultVariants: { tone: "accent" },
})

const tickVariants = cva("", {
  variants: {
    tone: {
      ink: "stroke-ink",
      accent: "stroke-accent",
      warn: "stroke-warn",
      mute: "stroke-ink-mute",
    },
  },
  defaultVariants: { tone: "ink" },
})

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}

function defaultFormat(v: number): string {
  return `${v > 0 ? "+" : ""}${Number.isInteger(v) ? v : v.toFixed(2)}`
}

/** Fraction (0..1) of `value` on a `[min, max]` axis, clamped. */
function frac(value: number, min: number, max: number): number {
  if (!(max > min)) return 0
  return Math.min(1, Math.max(0, (value - min) / (max - min)))
}

export type DivergingBarItem = {
  /** Stable key; falls back to the label. */
  id?: string
  label: string
  /** `null` / non-finite renders an empty track and an em dash. */
  value: number | null | undefined
  /** Preformatted value text; overrides `format`. */
  display?: string
  tone?: BarTone
}

export type DivergingBarsProps = Omit<React.ComponentProps<"div">, "children"> & {
  items: DivergingBarItem[]
  /** Half-axis magnitude. Defaults to the largest |value| in `items`. */
  max?: number
  /** `desc` ranks high to low, `abs` by magnitude; `none` keeps input order. */
  sort?: "none" | "desc" | "abs"
  /** `signed`: up/down by direction. `accent`: accent both ways. */
  tone?: "signed" | "accent"
  format?: (value: number) => string
  /** Accessible name for the whole chart. */
  label?: string
  emptyLabel?: string
}

function DivergingBars({
  items,
  max,
  sort = "none",
  tone = "signed",
  format = defaultFormat,
  label = "Ranked signed values",
  emptyLabel = "No data",
  className,
  ...props
}: DivergingBarsProps) {
  const rows = React.useMemo(() => {
    const list = [...items]
    if (sort === "desc") {
      list.sort(
        (a, b) =>
          (isNum(b.value) ? b.value : -Infinity) - (isNum(a.value) ? a.value : -Infinity)
      )
    } else if (sort === "abs") {
      list.sort(
        (a, b) =>
          Math.abs(isNum(b.value) ? b.value : 0) - Math.abs(isNum(a.value) ? a.value : 0)
      )
    }
    return list
  }, [items, sort])

  if (rows.length === 0) {
    return (
      <div
        data-slot="diverging-bars"
        data-empty=""
        className={cn("font-mono text-xs text-ink-mute", className)}
        {...props}
      >
        {emptyLabel}
      </div>
    )
  }

  const half =
    isNum(max) && max > 0
      ? max
      : Math.max(0, ...rows.map((r) => (isNum(r.value) ? Math.abs(r.value) : 0)))
  const text = (r: DivergingBarItem) =>
    r.display ?? (isNum(r.value) ? format(r.value) : "—")
  const summary = `${label}: ${rows.map((r) => `${r.label} ${text(r)}`).join(", ")}`

  return (
    <div
      data-slot="diverging-bars"
      role="img"
      aria-label={summary}
      className={cn("flex flex-col gap-1 font-mono text-xs tabular-nums", className)}
      {...props}
    >
      {rows.map((r) => {
        const v = isNum(r.value) ? r.value : null
        const w = v !== null && half > 0 ? (Math.min(half, Math.abs(v)) / half) * 50 : 0
        const t: BarTone =
          r.tone ?? (tone === "accent" ? "accent" : v !== null && v < 0 ? "down" : "up")
        return (
          <div
            key={r.id ?? r.label}
            data-slot="diverging-bars-row"
            aria-hidden
            className="grid grid-cols-[minmax(4rem,9rem)_minmax(0,1fr)_4.5rem] items-center gap-2"
          >
            <span className="truncate text-ink-soft" title={r.label}>
              {r.label}
            </span>
            <svg
              viewBox="0 0 100 10"
              preserveAspectRatio="none"
              className="block h-3 w-full bg-surface"
              focusable="false"
            >
              {v !== null && w > 0 ? (
                <rect
                  data-slot="diverging-bars-fill"
                  data-tone={t}
                  className={fillVariants({ tone: t })}
                  x={v >= 0 ? 50 : 50 - w}
                  y={1}
                  width={w}
                  height={8}
                />
              ) : null}
              <line
                x1={50}
                x2={50}
                y1={0}
                y2={10}
                className="stroke-ink-mute"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <span className={cn("text-end", v === null ? "text-ink-mute" : "text-ink")}>
              {text(r)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export type ScoreBarMarker = {
  /** `null` / non-finite markers are dropped, never drawn at the centre. */
  value: number | null | undefined
  label: string
  tone?: "ink" | "accent" | "warn" | "mute"
}

export type ScoreBarProps = Omit<React.ComponentProps<"div">, "children"> & {
  /** `null` draws the empty track. */
  value: number | null | undefined
  /** Axis bounds. Default symmetric -1..1 (zero-centred). */
  min?: number
  max?: number
  /** Fill grows from this value (default 0 clamped into the axis). */
  origin?: number
  /** Reference ticks (prior, baseline, ...). */
  ticks?: ScoreBarMarker[]
  /** Target marker, drawn dashed and full height. */
  target?: { value: number | null | undefined; label?: string }
  tone?: "signed" | BarTone
  format?: (value: number) => string
  /** Accessible name, e.g. the row subject. */
  label?: string
}

function ScoreBar({
  value,
  min = -1,
  max = 1,
  origin,
  ticks = [],
  target,
  tone = "signed",
  format = defaultFormat,
  label = "Score",
  className,
  ...props
}: ScoreBarProps) {
  const v = isNum(value) ? value : null
  const originValue = isNum(origin) ? origin : Math.min(max, Math.max(min, 0))
  const o = frac(originValue, min, max) * 100
  const end = v === null ? o : frac(v, min, max) * 100
  const t: BarTone =
    tone === "signed" ? (v !== null && v < originValue ? "down" : "up") : tone
  const liveTicks = ticks.filter((k) => isNum(k.value))
  const targetX = target && isNum(target.value) ? frac(target.value, min, max) * 100 : null
  const parts = [
    `${label} ${v === null ? "no data" : format(v)}`,
    ...liveTicks.map((k) => `${k.label} ${format(k.value as number)}`),
    ...(target && isNum(target.value)
      ? [`${target.label ?? "Target"} ${format(target.value)}`]
      : []),
  ]

  return (
    <div
      data-slot="score-bar"
      data-empty={v === null ? "" : undefined}
      role="img"
      aria-label={parts.join(", ")}
      className={cn("w-full min-w-16", className)}
      {...props}
    >
      <svg
        viewBox="0 0 100 12"
        preserveAspectRatio="none"
        className="block h-3 w-full bg-surface"
        focusable="false"
      >
        {v !== null && end !== o ? (
          <rect
            data-slot="score-bar-fill"
            data-tone={t}
            className={fillVariants({ tone: t })}
            x={Math.min(o, end)}
            y={3}
            width={Math.abs(end - o)}
            height={6}
          />
        ) : null}
        <line
          x1={o}
          x2={o}
          y1={0}
          y2={12}
          className="stroke-ink-mute"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
        {liveTicks.map((k, i) => {
          const x = frac(k.value as number, min, max) * 100
          return (
            <line
              key={`${k.label}-${i}`}
              data-slot="score-bar-tick"
              className={tickVariants({ tone: k.tone })}
              x1={x}
              x2={x}
              y1={1}
              y2={11}
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            >
              <title>{k.label}</title>
            </line>
          )
        })}
        {targetX !== null ? (
          <line
            data-slot="score-bar-target"
            className="stroke-accent"
            x1={targetX}
            x2={targetX}
            y1={0}
            y2={12}
            strokeWidth={2}
            strokeDasharray="2 2"
            vectorEffect="non-scaling-stroke"
          >
            <title>{target?.label ?? "Target"}</title>
          </line>
        ) : null}
      </svg>
    </div>
  )
}

export { DivergingBars, ScoreBar }
