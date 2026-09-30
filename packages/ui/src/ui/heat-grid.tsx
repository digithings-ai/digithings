/**
 * HeatGrid + CalendarHeatmap — SVG intensity grids on a stepped tone scale.
 *
 *   - `HeatGrid`        — rows x cols matrix; `sequential` (one tone, low..high)
 *                         or `diverging` (two tones about a midpoint).
 *   - `CalendarHeatmap` — day cells in week columns with a `unit` noun
 *                         ("contributions", "docs", "events"). Generalises the
 *                         app-facing `RepoHeatmap` (components/repo-activity),
 *                         which stays as the repo-specific, heat-graph based
 *                         wrapper; this part reuses its pure `levelFor` step
 *                         function rather than duplicating it.
 *
 * SVG, SSR-safe, presentational. Fills are `color-mix()` of kit token vars
 * (no colour literals). Diverging palette: `health` (accent / warn, default)
 * or `pnl` (up / down) for genuinely signed P&L matrices.
 */
import * as React from "react"

import { cn } from "../lib/utils"
import { levelFor, type HeatDay } from "../components/repo-activity/heatmap"

export type HeatPalette = "health" | "pnl"

const STEPS = [0, 22, 45, 70, 100] // 5 levels: 0 = empty

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}

function mix(token: string, pct: number): string {
  return `color-mix(in srgb, var(--${token}) ${pct}%, transparent)`
}

const EMPTY_FILL = "color-mix(in srgb, var(--ink) 6%, transparent)"

/** Quantise `t` in 0..1 to a level 1..4 (0 is reserved for empty / zero). */
function step(t: number): 1 | 2 | 3 | 4 {
  return Math.min(4, Math.max(1, Math.ceil(t * 4))) as 1 | 2 | 3 | 4
}

export type HeatGridProps = Omit<React.ComponentProps<"div">, "children"> & {
  rows: string[]
  cols: string[]
  /** `values[r][c]`; `null` / missing draws an empty hairline cell. */
  values: Array<Array<number | null | undefined>>
  scale?: "sequential" | "diverging"
  /** Diverging colours: `health` accent/warn, `pnl` up/down. */
  palette?: HeatPalette
  /** Sequential: `[min, max]`. Diverging: symmetric about `midpoint` by max |delta|. Defaults to data. */
  domain?: [number, number]
  /** Diverging pivot (default 0). */
  midpoint?: number
  format?: (value: number) => string
  /** Print each cell's value inside it. */
  showValues?: boolean
  /** Cell size in px. */
  cellWidth?: number
  cellHeight?: number
  /** Width reserved for row labels, px. */
  labelWidth?: number
  label?: string
  emptyLabel?: string
}

function fmtDefault(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
}

function HeatGrid({
  rows,
  cols,
  values,
  scale = "sequential",
  palette = "health",
  domain,
  midpoint = 0,
  format = fmtDefault,
  showValues = false,
  cellWidth = 32,
  cellHeight = 22,
  labelWidth = 72,
  label = "Heat grid",
  emptyLabel = "No data",
  className,
  ...props
}: HeatGridProps) {
  const flat = values.flat().filter(isNum)
  if (rows.length === 0 || cols.length === 0 || flat.length === 0) {
    return (
      <div
        data-slot="heat-grid"
        data-empty=""
        className={cn("font-mono text-xs text-ink-mute", className)}
        {...props}
      >
        {emptyLabel}
      </div>
    )
  }

  const lo = domain ? domain[0] : Math.min(...flat)
  const hi = domain ? domain[1] : Math.max(...flat)
  const reach = domain
    ? Math.max(Math.abs(hi - midpoint), Math.abs(lo - midpoint))
    : Math.max(...flat.map((v) => Math.abs(v - midpoint)))
  const pos = palette === "pnl" ? "up" : "accent"
  const neg = palette === "pnl" ? "down" : "warn"

  const level = (v: number): { fill: string; level: number; side: "pos" | "neg" | "flat" } => {
    if (scale === "diverging") {
      const d = v - midpoint
      if (d === 0 || reach === 0) return { fill: EMPTY_FILL, level: 0, side: "flat" }
      const l = step(Math.min(1, Math.abs(d) / reach))
      return d > 0
        ? { fill: mix(pos, STEPS[l]), level: l, side: "pos" }
        : { fill: mix(neg, STEPS[l]), level: l, side: "neg" }
    }
    const span = hi - lo
    if (span <= 0) return { fill: mix("accent", STEPS[2]), level: 2, side: "pos" }
    const l = step(Math.min(1, Math.max(0, (v - lo) / span)))
    return { fill: mix("accent", STEPS[l]), level: l, side: "pos" }
  }

  const gap = 2
  const headH = 16
  const width = labelWidth + cols.length * (cellWidth + gap)
  const height = headH + rows.length * (cellHeight + gap)
  const summary = `${label}: ${rows.length} rows by ${cols.length} columns, values ${format(
    Math.min(...flat)
  )} to ${format(Math.max(...flat))}`

  return (
    <div
      data-slot="heat-grid"
      data-scale={scale}
      className={cn("max-w-full overflow-x-auto font-mono", className)}
      {...props}
    >
      <svg
        role="img"
        aria-label={summary}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        focusable="false"
        className="block"
      >
        {cols.map((c, ci) => (
          <text
            key={`c-${ci}`}
            x={labelWidth + ci * (cellWidth + gap) + cellWidth / 2}
            y={11}
            textAnchor="middle"
            className="fill-ink-mute text-[10px]"
          >
            {c}
          </text>
        ))}
        {rows.map((r, ri) => {
          const y = headH + ri * (cellHeight + gap)
          return (
            <g key={`r-${ri}`}>
              <text
                x={labelWidth - 6}
                y={y + cellHeight / 2 + 3.5}
                textAnchor="end"
                className="fill-ink-soft text-[10px]"
              >
                {r}
              </text>
              {cols.map((c, ci) => {
                const raw = values[ri]?.[ci]
                const x = labelWidth + ci * (cellWidth + gap)
                if (!isNum(raw)) {
                  return (
                    <rect
                      key={`x-${ri}-${ci}`}
                      data-slot="heat-grid-cell"
                      data-empty=""
                      x={x}
                      y={y}
                      width={cellWidth}
                      height={cellHeight}
                      className="fill-transparent stroke-hair"
                      strokeWidth={1}
                    >
                      <title>{`${r} / ${c}: no data`}</title>
                    </rect>
                  )
                }
                const l = level(raw)
                return (
                  <g key={`x-${ri}-${ci}`}>
                    <rect
                      data-slot="heat-grid-cell"
                      data-level={l.level}
                      data-side={l.side}
                      x={x}
                      y={y}
                      width={cellWidth}
                      height={cellHeight}
                      style={{ fill: l.fill }}
                    >
                      <title>{`${r} / ${c}: ${format(raw)}`}</title>
                    </rect>
                    {showValues ? (
                      <text
                        x={x + cellWidth / 2}
                        y={y + cellHeight / 2 + 3.5}
                        textAnchor="middle"
                        className="fill-ink text-[10px] tabular-nums"
                        pointerEvents="none"
                      >
                        {format(raw)}
                      </text>
                    ) : null}
                  </g>
                )
              })}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export type CalendarHeatmapProps = Omit<React.ComponentProps<"div">, "children"> & {
  /** Consecutive or sparse UTC days `{ date: "YYYY-MM-DD", count }`; sorted internally. */
  days: HeatDay[]
  /** Noun for tooltips and the summary ("contributions", "events"). */
  unit?: string | { singular: string; plural: string }
  /** Cell edge in px. */
  cell?: number
  showLegend?: boolean
  emptyLabel?: string
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

function CalendarHeatmap({
  days,
  unit = "contributions",
  cell = 11,
  showLegend = true,
  emptyLabel = "No data",
  className,
  ...props
}: CalendarHeatmapProps) {
  const valid = days
    .filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d.date) && isNum(d.count))
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
  if (valid.length === 0) {
    return (
      <div
        data-slot="calendar-heatmap"
        data-empty=""
        className={cn("font-mono text-xs text-ink-mute", className)}
        {...props}
      >
        {emptyLabel}
      </div>
    )
  }

  const nouns = typeof unit === "string" ? { singular: unit.replace(/s$/, ""), plural: unit } : unit
  const noun = (n: number) => (n === 1 ? nouns.singular : nouns.plural)
  const total = valid.reduce((s, d) => s + d.count, 0)
  const max = valid.reduce((m, d) => Math.max(m, d.count), 0)

  const gap = 3
  const pitch = cell + gap
  const dayIndex = (iso: string) => new Date(`${iso}T00:00:00Z`).getUTCDay()
  const startMs = Date.parse(`${valid[0].date}T00:00:00Z`)
  const startSunday = startMs - dayIndex(valid[0].date) * 86_400_000
  const place = (iso: string) => {
    const ms = Date.parse(`${iso}T00:00:00Z`)
    return { col: Math.floor((ms - startSunday) / (7 * 86_400_000)), row: dayIndex(iso) }
  }
  const cells = valid.map((d) => ({ ...d, ...place(d.date) }))
  const cols = Math.max(...cells.map((c) => c.col)) + 1

  const headH = 14
  const dayW = 24
  const width = dayW + cols * pitch
  const height = headH + 7 * pitch

  const monthLabels: Array<{ col: number; text: string }> = []
  let lastMonth = -1
  for (const c of cells) {
    const m = Number(c.date.slice(5, 7)) - 1
    if (m !== lastMonth && c.row <= 6) {
      // Label the first column that starts a new month, skipping a crowded first column.
      if (monthLabels.length === 0 || c.col - monthLabels[monthLabels.length - 1].col >= 3) {
        monthLabels.push({ col: c.col, text: MONTHS[m] })
      }
      lastMonth = m
    }
  }

  const summary = `${total.toLocaleString("en-US")} ${noun(total)} from ${valid[0].date} to ${
    valid[valid.length - 1].date
  }`

  return (
    <div
      data-slot="calendar-heatmap"
      className={cn("max-w-full overflow-x-auto font-mono", className)}
      {...props}
    >
      <svg
        role="img"
        aria-label={summary}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        focusable="false"
        className="block"
      >
        {monthLabels.map((m) => (
          <text
            key={`${m.col}-${m.text}`}
            x={dayW + m.col * pitch}
            y={10}
            className="fill-ink-mute text-[10px]"
          >
            {m.text}
          </text>
        ))}
        {[1, 3, 5].map((r) => (
          <text
            key={r}
            x={0}
            y={headH + r * pitch + cell - 1}
            className="fill-ink-mute text-[10px]"
          >
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][r]}
          </text>
        ))}
        {cells.map((c) => {
          const l = levelFor(c.count, max)
          return (
            <rect
              key={c.date}
              data-slot="calendar-heatmap-cell"
              data-level={l}
              x={dayW + c.col * pitch}
              y={headH + c.row * pitch}
              width={cell}
              height={cell}
              style={{ fill: l === 0 ? EMPTY_FILL : mix("accent", STEPS[l]) }}
            >
              <title>{`${c.date}: ${c.count} ${noun(c.count)}`}</title>
            </rect>
          )
        })}
      </svg>
      {showLegend ? (
        <div aria-hidden className="mt-1 flex items-center gap-1 text-[10px] text-ink-mute">
          <span>Less</span>
          {[0, 1, 2, 3, 4].map((l) => (
            <svg key={l} width={cell} height={cell} focusable="false">
              <rect
                width={cell}
                height={cell}
                data-level={l}
                style={{ fill: l === 0 ? EMPTY_FILL : mix("accent", STEPS[l]) }}
              />
            </svg>
          ))}
          <span>More</span>
        </div>
      ) : null}
    </div>
  )
}

export { HeatGrid, CalendarHeatmap }
