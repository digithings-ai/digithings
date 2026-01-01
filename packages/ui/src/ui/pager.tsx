"use client"

/**
 * Pager — the prev/next wayfinding control with a fixed middle slot
 * (`PagerPage` cells, a page count, a date), promoted from the controls layer
 * into the kit (#4306, batch K3). Disabled edges around a middle column that
 * stays put while its label width changes. Two dresses: "reference" (default,
 * per-cell hairline) and "capsule" (dashboard's shipped one-capsule look —
 * borderless chevrons pinned at the ends). The `.nb-pager*` / `.nb-page*`
 * dress is translated into token utilities here, so the controls CSS can
 * retire. This is distinct from {@link Pagination}, the numbered page trail.
 */

import type { ComponentPropsWithoutRef, HTMLAttributes, ReactNode } from "react"

import { cn } from "../lib/utils"

const BASE_ITEM =
  "min-w-[2rem] h-[2rem] px-[0.6rem] border border-hair bg-surface font-mono text-[0.72rem] text-ink-soft transition-colors"

const BASE_EDGE = cn(
  BASE_ITEM,
  "cursor-pointer enabled:hover:text-ink enabled:hover:border-[color-mix(in_srgb,var(--accent)_45%,var(--hair))] disabled:cursor-not-allowed disabled:opacity-40",
)

const CAPSULE_EDGE =
  "min-w-0 cursor-pointer border-0 bg-transparent p-0 text-ink-mute transition-colors duration-150 enabled:hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"

export type PagerProps = HTMLAttributes<HTMLDivElement> & {
  onPrev?: () => void
  onNext?: () => void
  prevDisabled?: boolean
  nextDisabled?: boolean
  prevLabel?: ReactNode
  nextLabel?: ReactNode
  /** Set these when the edge labels are bare glyphs (chevrons). */
  prevAriaLabel?: string
  nextAriaLabel?: string
  /** Middle slot — PagerPage cells, or any label (a date, "3 / 12", …). */
  children?: ReactNode
  /** Visual dress — "reference" (default) or dashboard's "capsule". */
  dress?: "reference" | "capsule"
}

export function Pager({
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  prevLabel = "‹ prev",
  nextLabel = "next ›",
  prevAriaLabel,
  nextAriaLabel,
  children,
  className,
  dress = "reference",
  ...props
}: PagerProps) {
  const edge = dress === "capsule" ? CAPSULE_EDGE : BASE_EDGE
  return (
    <div
      data-slot="pager"
      data-dress={dress}
      className={cn(
        "inline-grid grid-cols-[auto_minmax(0,max-content)_auto] items-center gap-[0.3rem]",
        dress === "capsule" &&
          "grid-cols-[auto_1fr_auto] gap-[0.5rem] border border-hair bg-term-bg px-[0.625rem] py-[0.375rem] font-mono text-[12.5px] tabular-nums",
        className,
      )}
      {...props}
    >
      <button
        type="button"
        className={edge}
        disabled={prevDisabled}
        aria-label={prevAriaLabel}
        onClick={onPrev}
      >
        {prevLabel}
      </button>
      {/* Fixed middle column so capsule arrows stay pinned at the ends while
          the label width varies (date strings, page counts, …). */}
      <div className="flex min-w-0 items-center justify-center">{children}</div>
      <button
        type="button"
        className={edge}
        disabled={nextDisabled}
        aria-label={nextAriaLabel}
        onClick={onNext}
      >
        {nextLabel}
      </button>
    </div>
  )
}

export type PagerPageProps = ComponentPropsWithoutRef<"button"> & {
  /** The current page — wears the accent fill and aria-current="page". */
  current?: boolean
}

export function PagerPage({ current, className, ...props }: PagerPageProps) {
  return (
    <button
      type="button"
      data-slot="pager-page"
      aria-current={current ? "page" : undefined}
      className={cn(
        BASE_ITEM,
        "cursor-pointer",
        current
          ? "text-on-accent bg-accent border-accent"
          : "hover:text-ink hover:border-[color-mix(in_srgb,var(--accent)_45%,var(--hair))]",
        className,
      )}
      {...props}
    />
  )
}
