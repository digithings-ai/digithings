import * as React from "react"

import { cn } from "../lib/utils"

/**
 * Stat — dense KPI tile: mono micro-caps label, tabular value, optional delta
 * and a `spark` slot (pass a Sparkline or any small SVG). Distinct from
 * `StatCounter` in components/metrics, which is a count-up marketing strip;
 * no equivalent dense tile existed, so this is new. Delta tone is a caller
 * decision (`up`/`down` are P&L colours, so use them only for P&L deltas);
 * the default is neutral `mute`.
 */
type StatTone = "mute" | "accent" | "warn" | "up" | "down"

const TONE: Record<StatTone, string> = {
  mute: "text-ink-mute",
  accent: "text-accent",
  warn: "text-warn",
  up: "text-up",
  down: "text-down",
}

type StatProps = Omit<React.ComponentProps<"div">, "children"> & {
  label: React.ReactNode
  /** Null/undefined renders an em dash. */
  value: React.ReactNode
  /** Change readout, e.g. "+1.2%". Omitted when null. */
  delta?: React.ReactNode
  deltaTone?: StatTone
  /** Trailing sparkline / mini-chart slot. */
  spark?: React.ReactNode
  /** Small line under the value. */
  hint?: React.ReactNode
}

function Stat({
  label,
  value,
  delta,
  deltaTone = "mute",
  spark,
  hint,
  className,
  ...props
}: StatProps) {
  const empty = value === null || value === undefined || value === ""
  const hasDelta = delta !== null && delta !== undefined && delta !== ""
  return (
    <div
      data-slot="stat"
      className={cn(
        "flex items-end justify-between gap-3 border border-hair bg-surface p-3 font-mono",
        className
      )}
      {...props}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <span
          data-slot="stat-label"
          className="text-[0.65rem] uppercase tracking-wider text-ink-mute"
        >
          {label}
        </span>
        <span
          data-slot="stat-value"
          className={cn("text-lg leading-none tabular-nums", empty ? "text-ink-mute" : "text-ink")}
        >
          {empty ? "—" : value}
        </span>
        {hasDelta ? (
          <span data-slot="stat-delta" className={cn("text-xs tabular-nums", TONE[deltaTone])}>
            {delta}
          </span>
        ) : null}
        {hint ? <span className="text-xs text-ink-mute">{hint}</span> : null}
      </div>
      {spark ? (
        <div data-slot="stat-spark" className="shrink-0 text-ink-soft">
          {spark}
        </div>
      ) : null}
    </div>
  )
}

export { Stat }
export type { StatProps, StatTone }
