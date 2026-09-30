/**
 * RangeTrack — a low..high track with labelled level markers (current, entry,
 * stop, target, ...). Generalises the math in apps/dashboard
 * `RiskEnvelopeCell` (fraction = (value - low) / span; a reading outside the
 * range PINS to the end with a caret shape instead of overflowing, and a
 * zero-width range draws nothing rather than a fabricated midpoint).
 * `envelopeRange(stopPct, targetPct)` is the adapter that cell can use: the
 * axis is percent-vs-entry, `-down .. +up`, with an `entry` marker at 0.
 *
 * SVG, SSR-safe, presentational. Stop/target default to warn/accent (levels,
 * not P&L); pass `tone` to override.
 */
import * as React from "react"
import { cva } from "class-variance-authority"

import { cn } from "../lib/utils"

export type RangeMarkerKind = "current" | "entry" | "stop" | "target" | "level"
export type RangeTone = "ink" | "accent" | "warn" | "mute" | "up" | "down"

export type RangeMarker = {
  kind?: RangeMarkerKind
  /** `null` / non-finite markers are dropped. */
  value: number | null | undefined
  label?: string
  tone?: RangeTone
}

const strokeVariants = cva("", {
  variants: {
    tone: {
      ink: "stroke-ink",
      accent: "stroke-accent",
      warn: "stroke-warn",
      mute: "stroke-ink-mute",
      up: "stroke-up",
      down: "stroke-down",
    },
  },
  defaultVariants: { tone: "ink" },
})

const fillVariants = cva("", {
  variants: {
    tone: {
      ink: "fill-ink",
      accent: "fill-accent",
      warn: "fill-warn",
      mute: "fill-ink-mute",
      up: "fill-up",
      down: "fill-down",
    },
  },
  defaultVariants: { tone: "ink" },
})

const KIND_TONE: Record<RangeMarkerKind, RangeTone> = {
  current: "ink",
  entry: "accent",
  stop: "warn",
  target: "accent",
  level: "mute",
}

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}

/** Raw (unclamped) position of `value` on `[low, high]`, or null when the span is empty. */
export function rangeFraction(value: number, low: number, high: number): number | null {
  const span = high - low
  return span > 0 ? (value - low) / span : null
}

/** The RiskEnvelopeCell axis: percent vs entry, `-|stop| .. +|target|`. Missing sides are 0. */
export function envelopeRange(
  stopPct: number | null | undefined,
  targetPct: number | null | undefined
): { low: number; high: number } {
  return {
    low: -(isNum(stopPct) ? Math.abs(stopPct) : 0),
    high: isNum(targetPct) ? Math.abs(targetPct) : 0,
  }
}

function defaultFormat(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
}

export type RangeTrackProps = Omit<React.ComponentProps<"div">, "children"> & {
  low: number | null | undefined
  high: number | null | undefined
  markers?: RangeMarker[]
  /** Tint left of the `entry` marker warn and right of it accent (envelope look). */
  envelope?: boolean
  /** Print low/high values under the track ends. */
  showEnds?: boolean
  format?: (value: number) => string
  /** Accessible name prefix. */
  label?: string
  emptyLabel?: string
}

function RangeTrack({
  low,
  high,
  markers = [],
  envelope = false,
  showEnds = false,
  format = defaultFormat,
  label = "Range",
  emptyLabel = "—",
  className,
  ...props
}: RangeTrackProps) {
  if (!isNum(low) || !isNum(high) || !(high > low)) {
    return (
      <div
        data-slot="range-track"
        data-empty=""
        role="img"
        aria-label={`${label}: no range`}
        className={cn("font-mono text-xs text-ink-mute", className)}
        {...props}
      >
        {emptyLabel}
      </div>
    )
  }

  const placed = markers
    .filter((m) => isNum(m.value))
    .map((m) => {
      const raw = rangeFraction(m.value as number, low, high) as number
      const pinned: "low" | "high" | null = raw < 0 ? "low" : raw > 1 ? "high" : null
      const kind = m.kind ?? "level"
      return {
        ...m,
        kind,
        tone: m.tone ?? KIND_TONE[kind],
        x: Math.min(1, Math.max(0, raw)) * 100,
        pinned,
      }
    })
  const entry = placed.find((m) => m.kind === "entry")

  const describe = (m: (typeof placed)[number]) =>
    `${m.label ?? m.kind} ${format(m.value as number)}${
      m.pinned ? (m.pinned === "high" ? " (beyond the high end)" : " (below the low end)") : ""
    }`
  const summary = [`${label} ${format(low)} to ${format(high)}`, ...placed.map(describe)].join(
    ", "
  )

  return (
    <div
      data-slot="range-track"
      role="img"
      aria-label={summary}
      className={cn("w-full min-w-16 font-mono text-[10px] tabular-nums text-ink-mute", className)}
      {...props}
    >
      <svg
        viewBox="0 0 100 14"
        preserveAspectRatio="none"
        className="block h-3.5 w-full overflow-visible"
        focusable="false"
      >
        <rect x={0} y={5} width={100} height={4} className="fill-surface" />
        {envelope && entry ? (
          <>
            <rect x={0} y={5} width={entry.x} height={4} className="fill-warn" fillOpacity={0.4} />
            <rect
              x={entry.x}
              y={5}
              width={100 - entry.x}
              height={4}
              className="fill-accent"
              fillOpacity={0.4}
            />
          </>
        ) : null}
        <line
          x1={0}
          x2={100}
          y1={7}
          y2={7}
          className="stroke-hair"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
        {placed.map((m, i) =>
          m.pinned ? (
            // Pinned: an inward-pointing caret (shape, not colour) so it never reads as "on the boundary".
            <polygon
              key={`${m.kind}-${i}`}
              data-slot="range-track-marker"
              data-kind={m.kind}
              data-pinned={m.pinned}
              className={fillVariants({ tone: m.tone })}
              points={m.pinned === "high" ? "100,1 100,13 96,7" : "0,1 0,13 4,7"}
            >
              <title>{describe(m)}</title>
            </polygon>
          ) : (
            <line
              key={`${m.kind}-${i}`}
              data-slot="range-track-marker"
              data-kind={m.kind}
              className={strokeVariants({ tone: m.tone })}
              x1={m.x}
              x2={m.x}
              y1={m.kind === "current" ? 0 : 2}
              y2={m.kind === "current" ? 14 : 12}
              strokeWidth={m.kind === "current" ? 3 : 2}
              vectorEffect="non-scaling-stroke"
            >
              <title>{describe(m)}</title>
            </line>
          )
        )}
      </svg>
      {showEnds ? (
        <div aria-hidden className="mt-0.5 flex justify-between">
          <span>{format(low)}</span>
          <span>{format(high)}</span>
        </div>
      ) : null}
    </div>
  )
}

export { RangeTrack }
