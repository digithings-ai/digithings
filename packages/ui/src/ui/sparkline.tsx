/**
 * Sparkline — tiny inline SVG trend. Pure/presentational (SSR-safe, no canvas,
 * no fetching). `null`/NaN values break the line into gaps rather than being
 * interpolated. Tone `up`/`down` are P&L colours; use `accent`/`ink` for
 * non-P&L series.
 */
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../lib/utils"

const strokeTone = {
  ink: "stroke-ink",
  soft: "stroke-ink-soft",
  mute: "stroke-ink-mute",
  accent: "stroke-accent",
  warn: "stroke-warn",
  up: "stroke-up",
  down: "stroke-down",
} as const
const fillTone = {
  ink: "fill-ink",
  soft: "fill-ink-soft",
  mute: "fill-ink-mute",
  accent: "fill-accent",
  warn: "fill-warn",
  up: "fill-up",
  down: "fill-down",
} as const

const sparklineVariants = cva("inline-block shrink-0 align-middle overflow-visible", {
  variants: {
    tone: {
      ink: "",
      soft: "",
      mute: "",
      accent: "",
      warn: "",
      up: "",
      down: "",
    },
  },
  defaultVariants: { tone: "accent" },
})

type SparklineTone = keyof typeof strokeTone

type SparklineProps = Omit<
  React.ComponentProps<"svg">,
  "values" | "width" | "height"
> &
  VariantProps<typeof sparklineVariants> & {
    /** Series; `null`/`undefined`/NaN render as gaps. */
    values: ReadonlyArray<number | null | undefined>
    width?: number
    height?: number
    /** Dot on the last finite point. */
    lastDot?: boolean
    /** Fill under the line (faint). */
    area?: boolean
    /** Accessible name; defaults to a generated summary. */
    label?: string
  }

const PAD = 2

function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}

function Sparkline({
  values,
  tone,
  width = 96,
  height = 24,
  lastDot = true,
  area = false,
  label,
  className,
  ...props
}: SparklineProps) {
  const finite = values.filter(isNum)
  const t = (tone ?? "accent") as SparklineTone
  const summary =
    label ??
    (finite.length === 0
      ? "Trend: no data"
      : `Trend: ${finite.length} points, from ${finite[0]} to ${finite[finite.length - 1]}`)

  const base = cn(sparklineVariants({ tone: t }), className)

  if (finite.length === 0) {
    return (
      <svg
        data-slot="sparkline"
        data-empty=""
        role="img"
        aria-label={summary}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={base}
        {...props}
      >
        <line
          x1={PAD}
          x2={width - PAD}
          y1={height / 2}
          y2={height / 2}
          strokeDasharray="2 3"
          className="stroke-hair"
          strokeWidth={1}
        />
      </svg>
    )
  }

  const min = Math.min(...finite)
  const max = Math.max(...finite)
  const span = max - min
  const n = values.length
  const x = (i: number) =>
    n <= 1 ? width / 2 : PAD + (i * (width - PAD * 2)) / (n - 1)
  const y = (v: number) =>
    span === 0
      ? height / 2
      : height - PAD - ((v - min) * (height - PAD * 2)) / span

  // Split into runs of consecutive finite values.
  const runs: Array<Array<[number, number]>> = []
  let cur: Array<[number, number]> = []
  let lastIdx = -1
  values.forEach((v, i) => {
    if (isNum(v)) {
      cur.push([x(i), y(v)])
      lastIdx = i
    } else if (cur.length) {
      runs.push(cur)
      cur = []
    }
  })
  if (cur.length) runs.push(cur)

  const f = (v: number) => Math.round(v * 100) / 100
  const line = (r: Array<[number, number]>) =>
    r.map(([px, py], i) => `${i ? "L" : "M"}${f(px)} ${f(py)}`).join(" ")
  const lastV = values[lastIdx] as number

  return (
    <svg
      data-slot="sparkline"
      data-tone={t}
      role="img"
      aria-label={summary}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={base}
      {...props}
    >
      {area &&
        runs
          .filter((r) => r.length > 1)
          .map((r, i) => (
            <path
              key={`a${i}`}
              d={`${line(r)} L${f(r[r.length - 1][0])} ${height} L${f(r[0][0])} ${height} Z`}
              className={fillTone[t]}
              fillOpacity={0.12}
              stroke="none"
            />
          ))}
      {runs.map((r, i) =>
        r.length > 1 ? (
          <path
            key={`l${i}`}
            d={line(r)}
            fill="none"
            strokeWidth={1.25}
            strokeLinejoin="round"
            strokeLinecap="square"
            vectorEffect="non-scaling-stroke"
            className={strokeTone[t]}
          />
        ) : (
          <circle
            key={`p${i}`}
            cx={f(r[0][0])}
            cy={f(r[0][1])}
            r={1}
            className={fillTone[t]}
          />
        )
      )}
      {lastDot && (
        <circle
          cx={f(x(lastIdx))}
          cy={f(y(lastV))}
          r={2}
          className={fillTone[t]}
        />
      )}
    </svg>
  )
}

export { Sparkline, sparklineVariants }
export type { SparklineProps, SparklineTone }
