/**
 * CompositionBar — stacked / 100% share bar. `mode="share"` (default)
 * normalises segments to fill the bar; `mode="stacked"` sizes them against
 * `total` (default: their sum) so a partial bar stays partial. A `cash`
 * segment is drawn in `hair` so it reads as "not deployed". Segments cycle
 * neutral/accent tones by default (never up/down). Optional `onSelect` turns
 * segments into buttons. Pure/presentational, SSR-safe.
 */
import * as React from "react"
import { cva } from "class-variance-authority"

import { cn } from "../lib/utils"

const segmentVariants = cva("block h-full min-w-px", {
  variants: {
    tone: {
      accent: "bg-accent",
      ink: "bg-ink",
      soft: "bg-ink-soft",
      mute: "bg-ink-mute",
      weak: "bg-accent-weak",
      warn: "bg-warn",
      cash: "bg-hair",
    },
  },
  defaultVariants: { tone: "accent" },
})

type SegmentTone = "accent" | "ink" | "soft" | "mute" | "weak" | "warn" | "cash"

const CYCLE: SegmentTone[] = ["accent", "ink", "soft", "mute", "weak"]

type CompositionSegment = {
  key?: string
  label: string
  value: number
  tone?: SegmentTone
  /** Cash / undeployed remainder: styled as `cash` tone. */
  cash?: boolean
}

type CompositionBarProps = Omit<
  React.ComponentProps<"div">,
  "children" | "onSelect"
> & {
  segments: ReadonlyArray<CompositionSegment>
  mode?: "share" | "stacked"
  /** Denominator for `stacked` mode. */
  total?: number
  /** Bar height in px. */
  height?: number
  /** Render a legend (label + percent) under the bar. */
  legend?: boolean
  onSelect?: (segment: CompositionSegment, index: number) => void
  /** Accessible name; defaults to a generated summary. */
  label?: string
}

function pct(n: number) {
  return `${Math.round(n * 10) / 10}%`
}

function CompositionBar({
  segments,
  mode = "share",
  total,
  height = 8,
  legend = false,
  onSelect,
  label,
  className,
  ...props
}: CompositionBarProps) {
  const valid = segments.filter((s) => Number.isFinite(s.value) && s.value > 0)
  const sum = valid.reduce((a, s) => a + s.value, 0)
  const denom = mode === "stacked" ? Math.max(total ?? sum, sum) : sum
  const share = (s: CompositionSegment) =>
    denom > 0 ? (s.value / denom) * 100 : 0
  const toneOf = (s: CompositionSegment, i: number): SegmentTone =>
    s.cash ? "cash" : (s.tone ?? CYCLE[i % CYCLE.length])
  const summary =
    label ??
    (valid.length === 0
      ? "Composition: no data"
      : `Composition: ${valid.map((s) => `${s.label} ${pct(share(s))}`).join(", ")}`)

  return (
    <div
      data-slot="composition-bar"
      data-mode={mode}
      className={cn("w-full", className)}
      {...props}
    >
      <div
        role="group"
        aria-label={summary}
        className="flex w-full gap-px border border-hair"
        style={{ height }}
      >
        {valid.length === 0 ? (
          <span
            data-slot="composition-bar-empty"
            className="block h-full flex-1 bg-transparent"
          />
        ) : (
          valid.map((s, i) => {
            const tone = toneOf(s, i)
            const common = {
              "data-slot": "composition-bar-segment",
              "data-tone": tone,
              title: `${s.label} ${pct(share(s))}`,
              "aria-label": `${s.label} ${pct(share(s))}`,
              className: cn(
                segmentVariants({ tone }),
                onSelect &&
                  "focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent hover:brightness-125"
              ),
              style: { width: `${share(s)}%` },
            } as const
            return onSelect ? (
              <button
                key={s.key ?? i}
                type="button"
                onClick={() => onSelect(s, i)}
                {...common}
              />
            ) : (
              <span key={s.key ?? i} role="img" {...common} />
            )
          })
        )}
      </div>
      {legend && valid.length > 0 && (
        <ul
          data-slot="composition-bar-legend"
          className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[0.7rem] text-ink-soft"
        >
          {valid.map((s, i) => (
            <li key={s.key ?? i} className="flex items-center gap-1.5">
              <span
                className={cn(
                  segmentVariants({ tone: toneOf(s, i) }),
                  "size-2 min-w-0"
                )}
                aria-hidden
              />
              <span>{s.label}</span>
              <span className="text-ink-mute">{pct(share(s))}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export { CompositionBar, segmentVariants as compositionSegmentVariants }
export type { CompositionBarProps, CompositionSegment, SegmentTone }
