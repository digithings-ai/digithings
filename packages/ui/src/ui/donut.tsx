"use client"

/**
 * Donut — share-of-whole ring with a ranked legend. Segments are normalised to
 * the ring; `cash` is drawn in `hair` so it reads as "not deployed". Tones cycle
 * neutral/accent (never up/down); repeats past the palette are dimmed so no two
 * neighbours share a fill. Hovering/focusing a legend row or arc highlights the
 * pair. `children` renders in the centre (e.g. "82% invested"). SVG only,
 * SSR-safe, data by props.
 */
import * as React from "react"

import { cn } from "../lib/utils"

type DonutTone = "accent" | "ink" | "soft" | "mute" | "weak" | "warn" | "cash"

type DonutSegment = {
  key?: string
  label: string
  value: number
  tone?: DonutTone
  /** Cash / undeployed remainder: styled as `cash` tone. */
  cash?: boolean
}

type DonutProps = Omit<React.ComponentProps<"div">, "children"> & {
  segments: ReadonlyArray<DonutSegment>
  /** Ring diameter in px. */
  size?: number
  /** Ring thickness in px. */
  thickness?: number
  /** Centre content. */
  children?: React.ReactNode
  /** Ranked legend beside the ring (label + percent). */
  legend?: boolean
  /** Accessible name; defaults to a generated summary. */
  label?: string
}

const stroke: Record<DonutTone, string> = {
  accent: "stroke-accent",
  ink: "stroke-ink",
  soft: "stroke-ink-soft",
  mute: "stroke-ink-mute",
  weak: "stroke-accent-weak",
  warn: "stroke-warn",
  cash: "stroke-hair",
}
const swatch: Record<DonutTone, string> = {
  accent: "bg-accent",
  ink: "bg-ink",
  soft: "bg-ink-soft",
  mute: "bg-ink-mute",
  weak: "bg-accent-weak",
  warn: "bg-warn",
  cash: "bg-hair",
}
const CYCLE: DonutTone[] = ["accent", "ink", "soft", "mute", "weak"]

function pct(n: number) {
  return `${Math.round(n * 10) / 10}%`
}

function Donut({
  segments,
  size = 132,
  thickness = 18,
  legend = true,
  label,
  className,
  children,
  ...props
}: DonutProps) {
  const [active, setActive] = React.useState<number | null>(null)
  const valid = segments.filter((s) => Number.isFinite(s.value) && s.value > 0)
  const sum = valid.reduce((a, s) => a + s.value, 0)
  const rows = valid.map((s, i) => {
    const tone: DonutTone = s.cash ? "cash" : (s.tone ?? CYCLE[i % CYCLE.length])
    // Second lap around the palette is dimmed so repeats stay distinguishable.
    const dim = !s.cash && !s.tone && Math.floor(i / CYCLE.length) % 2 === 1
    return { s, tone, dim, share: sum > 0 ? (s.value / sum) * 100 : 0 }
  })

  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  const gap = rows.length > 1 ? 1.5 : 0
  let offset = 0
  const arcs = rows.map((row) => {
    const len = (row.share / 100) * c
    const arc = { len: Math.max(0, len - gap), offset }
    offset += len
    return arc
  })

  const name =
    label ??
    (rows.length
      ? rows.map((row) => `${row.s.label} ${pct(row.share)}`).join(", ")
      : "No data")

  return (
    <div
      data-slot="donut"
      className={cn("flex flex-wrap items-center gap-x-5 gap-y-3", className)}
      {...props}
    >
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg
          role="img"
          aria-label={name}
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="-rotate-90"
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={thickness}
            className="stroke-hair/40"
          />
          {rows.map((row, i) => (
            <circle
              key={row.s.key ?? row.s.label}
              data-slot="donut-arc"
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              strokeWidth={active === i ? thickness + 3 : thickness}
              strokeDasharray={`${arcs[i].len} ${c - arcs[i].len}`}
              strokeDashoffset={-arcs[i].offset}
              className={cn(
                stroke[row.tone],
                row.dim && "opacity-60",
                active !== null && active !== i && "opacity-30",
                "transition-[opacity,stroke-width]"
              )}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
            >
              <title>{`${row.s.label} ${pct(row.share)}`}</title>
            </circle>
          ))}
        </svg>
        {children ? (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
            {children}
          </div>
        ) : null}
      </div>
      {legend && rows.length > 0 ? (
        <ul
          data-slot="donut-legend"
          className="grid min-w-0 flex-1 basis-40 gap-y-1 font-mono text-xs"
        >
          {rows.map((row, i) => (
            <li
              key={row.s.key ?? row.s.label}
              data-slot="donut-legend-row"
              tabIndex={0}
              className={cn(
                "flex items-center gap-2 outline-none focus-visible:ring-1 focus-visible:ring-accent/60",
                active !== null && active !== i && "opacity-50"
              )}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
            >
              <span
                aria-hidden
                className={cn(
                  "size-2 shrink-0",
                  swatch[row.tone],
                  row.dim && "opacity-60"
                )}
              />
              <span className="min-w-0 flex-1 truncate text-ink">{row.s.label}</span>
              <span className="tabular-nums text-ink-mute">{pct(row.share)}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export { Donut }
export type { DonutProps, DonutSegment, DonutTone }
