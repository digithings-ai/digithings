"use client"

/**
 * AllocationTreemap — squarified treemap, area = value, tone = a second
 * number (defaults to the value itself, so bigger reads stronger). No
 * equivalent existed in finance-charts / finance-tearsheet / metrics /
 * finance-composites, so this is a new part. SVG only, no fetching.
 *
 * Tone is a single-hue accent ramp (never up/down: allocation is not P&L).
 */
import * as React from "react"

import { cn } from "../lib/utils"

/** Ordered light-to-strong accent ramp. Literal strings so Tailwind sees them. */
export const TREEMAP_TONES = [
  "fill-accent/10",
  "fill-accent/20",
  "fill-accent/35",
  "fill-accent/50",
  "fill-accent/70",
] as const

export type TreemapItem = {
  id: string
  label: string
  value: number
  /** Drives the colour ramp; defaults to `value`. */
  tone?: number
  /** Secondary line, e.g. formatted weight. */
  detail?: string
}

export type TreemapRect = { x: number; y: number; w: number; h: number }

/** Squarified layout (Bruls et al.). Returns rects in input order; non-positive values get zero-area rects. */
export function squarify(values: number[], box: TreemapRect): TreemapRect[] {
  const out: TreemapRect[] = values.map(() => ({ x: box.x, y: box.y, w: 0, h: 0 }))
  const idx = values
    .map((v, i) => ({ v, i }))
    .filter((e) => Number.isFinite(e.v) && e.v > 0)
    .sort((a, b) => b.v - a.v)
  const total = idx.reduce((s, e) => s + e.v, 0)
  if (!total || box.w <= 0 || box.h <= 0) return out
  const scale = (box.w * box.h) / total
  let { x, y, w, h } = box
  let row: { v: number; i: number }[] = []

  const worst = (r: typeof row, side: number) => {
    const s = r.reduce((a, e) => a + e.v * scale, 0)
    const max = Math.max(...r.map((e) => e.v * scale))
    const min = Math.min(...r.map((e) => e.v * scale))
    return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min))
  }
  const flush = () => {
    if (!row.length) return
    const s = row.reduce((a, e) => a + e.v * scale, 0)
    if (w >= h) {
      const rw = s / h
      let cy = y
      for (const e of row) {
        const eh = (e.v * scale) / rw
        out[e.i] = { x, y: cy, w: rw, h: eh }
        cy += eh
      }
      x += rw
      w -= rw
    } else {
      const rh = s / w
      let cx = x
      for (const e of row) {
        const ew = (e.v * scale) / rh
        out[e.i] = { x: cx, y, w: ew, h: rh }
        cx += ew
      }
      y += rh
      h -= rh
    }
    row = []
  }
  for (const e of idx) {
    const side = Math.min(w, h)
    if (row.length && worst([...row, e], side) > worst(row, side)) flush()
    row.push(e)
  }
  flush()
  return out
}

export type AllocationTreemapProps = {
  items: TreemapItem[]
  selectedId?: string | null
  onSelect?: (id: string) => void
  /** Formats the value shown under the label when `detail` is absent. */
  formatValue?: (n: number) => string
  label?: string
  emptyLabel?: string
  className?: string
}

const W = 640
const H = 320

export function AllocationTreemap({
  items,
  selectedId,
  onSelect,
  formatValue = (n) => `${Math.round(n * 10) / 10}`,
  label = "Allocation treemap",
  emptyLabel = "No allocation to show.",
  className,
}: AllocationTreemapProps) {
  const live = items.filter((i) => Number.isFinite(i.value) && i.value > 0)
  if (!live.length) {
    return (
      <div
        data-slot="treemap"
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
  const rects = squarify(
    live.map((i) => i.value),
    { x: 0, y: 0, w: W, h: H },
  )
  const tones = live.map((i) => i.tone ?? i.value)
  const lo = Math.min(...tones)
  const hi = Math.max(...tones)
  const step = (t: number) =>
    hi === lo
      ? 2
      : Math.min(
          TREEMAP_TONES.length - 1,
          Math.floor(((t - lo) / (hi - lo)) * TREEMAP_TONES.length),
        )
  const total = live.reduce((s, i) => s + i.value, 0)
  const summary = live
    .map((i) => `${i.label} ${Math.round((i.value / total) * 1000) / 10}%`)
    .join(", ")

  return (
    <figure data-slot="treemap" className={cn("m-0", className)}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={label}
        className="block h-auto w-full font-mono"
      >
        {live.map((it, i) => {
          const r = rects[i]
          const selected = it.id === selectedId
          const showText = r.w > 56 && r.h > 30
          const body = (
            <>
              <rect
                x={r.x}
                y={r.y}
                width={r.w}
                height={r.h}
                className={cn(
                  TREEMAP_TONES[step(tones[i])],
                  selected ? "stroke-accent" : "stroke-surface",
                )}
                strokeWidth={selected ? 2 : 1}
              />
              {showText ? (
                <text x={r.x + 6} y={r.y + 6} dominantBaseline="hanging" fontSize={11}>
                  <tspan className="fill-ink">{it.label}</tspan>
                  <tspan x={r.x + 6} dy={14} className="fill-ink-soft" fontSize={10}>
                    {it.detail ?? formatValue(it.value)}
                  </tspan>
                </text>
              ) : null}
            </>
          )
          return onSelect ? (
            <g
              key={it.id}
              data-slot="treemap-cell"
              role="button"
              tabIndex={0}
              aria-pressed={selected}
              aria-label={`${it.label} ${it.detail ?? formatValue(it.value)}`}
              className="cursor-pointer focus-visible:outline-none [&:focus-visible>rect]:stroke-accent"
              onClick={() => onSelect(it.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault()
                  onSelect(it.id)
                }
              }}
            >
              <title>{it.label}</title>
              {body}
            </g>
          ) : (
            <g key={it.id} data-slot="treemap-cell">
              <title>{it.label}</title>
              {body}
            </g>
          )
        })}
      </svg>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  )
}
