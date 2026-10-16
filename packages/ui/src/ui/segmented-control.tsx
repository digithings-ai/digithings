"use client"

/**
 * SegmentedControl — the range switch (#1548), promoted from the controls
 * layer into the kit (#4306, batch K1). Plain buttons wearing `aria-pressed`
 * inside a `role="group"` — deliberately NOT a tablist (the segments switch a
 * data range on the same view, they don't own tab panels). Two dresses:
 * "reference" (default, mono cells on surface / accent-weak selection) and
 * "accent" (dashboard's shipped look — sans font-medium cells, transparent
 * track, accent/20 wash + accent text on the selection). Token utilities only,
 * so `.nb-seg*` can retire.
 */

import type { HTMLAttributes, ReactNode } from "react"

import { cn } from "../lib/utils"

export type SegmentedOption<T extends string = string> = {
  value: T
  /** Defaults to the value itself. */
  label?: ReactNode
  disabled?: boolean
}

export type SegmentedControlProps<T extends string = string> = Omit<
  HTMLAttributes<HTMLDivElement>,
  "onChange"
> & {
  options: ReadonlyArray<T | SegmentedOption<T>>
  value: T
  onChange?: (value: T) => void
  /** Visual dress — "reference" (default) or dashboard's "accent". */
  dress?: "reference" | "accent"
}

export function SegmentedControl<T extends string = string>({
  options,
  value,
  onChange,
  className,
  dress = "reference",
  ...props
}: SegmentedControlProps<T>) {
  const accent = dress === "accent"
  return (
    <div
      data-slot="segmented"
      role="group"
      className={cn(
        "inline-flex overflow-hidden rounded-none border border-hair",
        className,
      )}
      {...props}
    >
      {options.map((option) => {
        const opt = typeof option === "string" ? { value: option } : option
        return (
          <button
            key={opt.value}
            type="button"
            className={cn(
              "inline-flex cursor-pointer items-center justify-center rounded-none bg-surface px-[0.85rem] py-[0.4rem] font-mono text-[0.72rem] text-ink-mute transition-colors [border-inline-start:1px_solid_var(--hair)] first:[border-inline-start:0] hover:text-ink-soft aria-pressed:bg-accent-weak aria-pressed:text-ink disabled:cursor-not-allowed",
              accent &&
                "bg-transparent px-3 py-[0.375rem] font-sans text-xs font-medium text-ink-mute hover:bg-ink/4 hover:text-ink aria-pressed:bg-accent/20 aria-pressed:text-accent",
            )}
            aria-pressed={opt.value === value}
            disabled={opt.disabled}
            onClick={() => onChange?.(opt.value)}
          >
            {opt.label ?? opt.value}
          </button>
        )
      })}
    </div>
  )
}
