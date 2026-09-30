/**
 * StatusDot + StatusStrip — health-state primitives. Tones are health, not
 * P&L: `ok` = accent, `warn` = warn, `off` = ink-mute, `idle` = hollow (never
 * up/down). StatusStrip is N hairline cells, each with a tone and a label
 * exposed as a native tooltip (`title`) and an accessible name; cells become
 * buttons when `onSelect` is given. Pure/presentational, SSR-safe.
 */
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../lib/utils"

const statusDotVariants = cva("inline-block shrink-0 rounded-none", {
  variants: {
    tone: {
      ok: "bg-accent",
      warn: "bg-warn",
      off: "bg-ink-mute",
      idle: "border border-ink-mute bg-transparent",
    },
    size: { sm: "size-1.5", md: "size-2", lg: "size-2.5" },
  },
  defaultVariants: { tone: "ok", size: "md" },
})

type StatusTone = NonNullable<VariantProps<typeof statusDotVariants>["tone"]>

type StatusDotProps = Omit<React.ComponentProps<"span">, "children"> &
  VariantProps<typeof statusDotVariants> & {
    /** Accessible name; omit for a purely decorative dot. */
    label?: string
  }

function StatusDot({ tone, size, label, className, ...props }: StatusDotProps) {
  return (
    <span
      data-slot="status-dot"
      data-tone={tone ?? "ok"}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(statusDotVariants({ tone, size }), className)}
      {...props}
    />
  )
}

const cellVariants = cva("block h-full min-w-0 flex-1 basis-0", {
  variants: {
    tone: {
      ok: "bg-accent",
      warn: "bg-warn",
      off: "bg-ink-mute",
      idle: "bg-surface",
    },
  },
  defaultVariants: { tone: "ok" },
})

type StatusCell = {
  key?: string
  tone?: StatusTone
  /** Tooltip + accessible name for this cell. */
  label: string
}

type StatusStripProps = Omit<
  React.ComponentProps<"div">,
  "children" | "onSelect"
> & {
  cells: ReadonlyArray<StatusCell>
  /** Strip height in px. */
  height?: number
  /** Makes cells focusable buttons. */
  onSelect?: (cell: StatusCell, index: number) => void
  /** Accessible name for the whole strip. */
  label?: string
}

function StatusStrip({
  cells,
  height = 14,
  onSelect,
  label,
  className,
  style,
  ...props
}: StatusStripProps) {
  const counts = cells.reduce<Record<string, number>>((acc, c) => {
    const t = c.tone ?? "ok"
    acc[t] = (acc[t] ?? 0) + 1
    return acc
  }, {})
  const summary =
    label ??
    (cells.length === 0
      ? "Status: no data"
      : `Status: ${Object.entries(counts)
          .map(([t, n]) => `${n} ${t}`)
          .join(", ")}`)

  return (
    <div
      data-slot="status-strip"
      role="group"
      aria-label={summary}
      className={cn("flex w-full gap-px border border-hair bg-hair", className)}
      style={{ height, ...style }}
      {...props}
    >
      {cells.length === 0 ? (
        <span
          data-slot="status-strip-cell"
          data-tone="idle"
          className={cellVariants({ tone: "idle" })}
        />
      ) : (
        cells.map((c, i) => {
          const common = {
            "data-slot": "status-strip-cell",
            "data-tone": c.tone ?? "ok",
            title: c.label,
            "aria-label": c.label,
            className: cn(
              cellVariants({ tone: c.tone }),
              onSelect &&
                "focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent hover:brightness-125"
            ),
          } as const
          return onSelect ? (
            <button
              key={c.key ?? i}
              type="button"
              onClick={() => onSelect(c, i)}
              {...common}
            />
          ) : (
            <span key={c.key ?? i} role="img" {...common} />
          )
        })
      )}
    </div>
  )
}

export { StatusDot, StatusStrip, statusDotVariants }
export type { StatusDotProps, StatusStripProps, StatusCell, StatusTone }
