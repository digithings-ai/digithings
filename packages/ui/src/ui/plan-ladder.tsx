import * as React from "react"

import { cn } from "../lib/utils"

/**
 * PlanLadder — tier rungs, lowest first. The `current` rung is highlighted
 * (accent edge + weak fill); other rungs are `available`, or `locked` when
 * flagged. Copy (names, blurbs, prices) is entirely caller-supplied through
 * `name` / `detail` / `meta`; the kit hardcodes no pricing text.
 */
type PlanRung = {
  id: string
  name: React.ReactNode
  /** Short description line. */
  detail?: React.ReactNode
  /** Right-aligned slot — a price, a quota, an action. Caller's text. */
  meta?: React.ReactNode
  /** Rung the viewer cannot reach (plan-gated, contact-sales, ...). */
  locked?: boolean
}

type PlanLadderProps = Omit<React.ComponentProps<"ol">, "children"> & {
  rungs: readonly PlanRung[] | null | undefined
  /** Id of the rung the viewer is on. */
  current?: string | null
  /** Rendered when `rungs` is empty or null. */
  empty?: React.ReactNode
  /** Visible state words, so copy stays the caller's (i18n). */
  stateLabels?: { current?: string; locked?: string; available?: string }
}

function PlanLadder({
  rungs,
  current,
  empty = "No plans",
  stateLabels,
  className,
  "aria-label": ariaLabel = "Plans",
  ...props
}: PlanLadderProps) {
  const list = rungs ?? []
  if (list.length === 0) {
    return (
      <p data-slot="plan-ladder-empty" className="font-mono text-xs text-ink-mute">
        {empty}
      </p>
    )
  }
  const labels = {
    current: "Current",
    locked: "Locked",
    available: "Available",
    ...stateLabels,
  }
  return (
    <ol
      data-slot="plan-ladder"
      aria-label={ariaLabel}
      className={cn("flex flex-col border border-hair font-mono text-xs", className)}
      {...props}
    >
      {list.map((r) => {
        const state = r.id === current ? "current" : r.locked ? "locked" : "available"
        return (
          <li
            key={r.id}
            data-slot="plan-rung"
            data-state={state}
            aria-current={state === "current" ? "step" : undefined}
            className={cn(
              "flex items-center gap-3 border-b border-b-hair border-s-2 px-3 py-2.5 last:border-b-0",
              state === "current"
                ? "border-s-accent bg-accent-weak text-ink"
                : "border-s-transparent bg-surface",
              state === "locked" && "text-ink-mute",
              state === "available" && "text-ink-soft"
            )}
          >
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="truncate">{r.name}</span>
              {r.detail ? <span className="text-ink-mute">{r.detail}</span> : null}
            </div>
            {r.meta ? <span className="tabular-nums">{r.meta}</span> : null}
            <span
              data-slot="plan-rung-state"
              className={cn(
                "shrink-0 border px-1.5 py-0.5 uppercase tracking-wider",
                state === "current" ? "border-accent text-accent" : "border-hair text-ink-mute"
              )}
            >
              {labels[state]}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

export { PlanLadder }
export type { PlanLadderProps, PlanRung }
