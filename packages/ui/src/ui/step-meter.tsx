import * as React from "react"

import { cn } from "../lib/utils"

/**
 * StepMeter — segmented usage meter: `limit` equal cells, the first `value`
 * filled. Health, not P&L: accent while comfortable, warn at/over `warnAt`
 * (fraction of the limit, default 0.8), never up/down. Presentational and
 * SSR-safe (plain DOM, no canvas); exposes `role="meter"` semantics.
 */
type StepMeterProps = Omit<React.ComponentProps<"div">, "children"> & {
  /** Units used. Null/undefined/NaN renders an empty meter with an em dash. */
  value: number | null | undefined
  /** Total units. Non-positive or missing renders a single empty track. */
  limit: number | null | undefined
  /** Left label (what is being metered). */
  label?: React.ReactNode
  /** Fraction of `limit` at which the fill turns warn. Default 0.8. */
  warnAt?: number
  /** Unit suffix for the readout, e.g. "runs". */
  unit?: string
  /** Cap on drawn cells; above it the meter draws this many proportional cells. */
  maxSegments?: number
}

function StepMeter({
  value,
  limit,
  label,
  warnAt = 0.8,
  unit,
  maxSegments = 20,
  className,
  ...props
}: StepMeterProps) {
  const hasLimit = typeof limit === "number" && Number.isFinite(limit) && limit > 0
  const hasValue = typeof value === "number" && Number.isFinite(value)
  const used = hasValue ? Math.max(0, value) : 0
  const cells = hasLimit ? Math.min(Math.round(limit), Math.max(1, maxSegments)) : 1
  const ratio = hasLimit ? Math.min(1, used / limit) : 0
  const filled = Math.round(ratio * cells)
  const warn = hasLimit && hasValue && used / limit >= warnAt
  const over = hasLimit && hasValue && used > limit
  const readout = hasValue
    ? `${used}${hasLimit ? ` / ${limit}` : ""}${unit ? ` ${unit}` : ""}`
    : "—"
  const text = typeof label === "string" ? label : undefined

  return (
    <div
      data-slot="step-meter"
      data-state={warn ? "warn" : "ok"}
      className={cn("flex flex-col gap-1.5 font-mono text-xs", className)}
      {...props}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span data-slot="step-meter-label" className="text-ink-soft">
          {label}
        </span>
        <span
          data-slot="step-meter-readout"
          className={cn("tabular-nums", warn ? "text-warn" : "text-ink")}
        >
          {readout}
        </span>
      </div>
      <div
        role="meter"
        aria-label={text ?? "Usage"}
        aria-valuemin={0}
        aria-valuemax={hasLimit ? limit : undefined}
        aria-valuenow={hasValue ? used : undefined}
        aria-valuetext={
          hasValue ? `${readout}${over ? " (over limit)" : warn ? " (near limit)" : ""}` : "No data"
        }
        data-slot="step-meter-track"
        className="flex h-2 gap-px"
      >
        {Array.from({ length: cells }, (_, i) => (
          <span
            key={i}
            data-slot="step-meter-cell"
            data-filled={i < filled ? "true" : "false"}
            className={cn(
              "h-full flex-1 border border-hair",
              i < filled ? (warn ? "border-warn bg-warn" : "border-accent bg-accent") : "bg-surface"
            )}
          />
        ))}
      </div>
    </div>
  )
}

export { StepMeter }
export type { StepMeterProps }
