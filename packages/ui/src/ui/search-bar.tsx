"use client"
/**
 * SearchBar — a search field with a leading glyph, a clear affordance that
 * appears once there's input, and an optional trailing `hint` slot shown
 * while empty (the reference wears a `/` keycap), promoted from the controls
 * layer into the kit (#4306, batch K2). Controlled — the results pane stays
 * with the caller; the bar only owns the query.
 *
 * The `.ctl-search` / `.sb-*` dress is translated into token utilities here;
 * focus-within lights the accent ring, and the native WebKit search-cancel
 * affordance is suppressed in favour of the clear button.
 */
import type { InputHTMLAttributes, ReactNode } from "react"

import { cn } from "../lib/utils"

export type SearchBarProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange" | "type" | "className"
> & {
  value: string
  onChange: (query: string) => void
  /** Clears the query — defaults to onChange(""). */
  onClear?: () => void
  clearAriaLabel?: string
  /** Trailing slot shown while the query is empty (keycap hint etc.). */
  hint?: ReactNode
  /** Replaces the leading magnifier glyph. */
  glyph?: ReactNode
  /** Lands on the field wrapper, not the input. */
  className?: string
}

const MAGNIFIER = (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
  </svg>
)

export function SearchBar({
  value,
  onChange,
  onClear,
  clearAriaLabel = "Clear search",
  hint,
  glyph,
  className,
  "aria-label": ariaLabel = "Search",
  ...inputProps
}: SearchBarProps) {
  return (
    <div
      data-slot="search-bar"
      className={cn(
        "flex w-[min(100%,26rem)] items-center gap-[0.55rem] border border-hair bg-surface px-[0.7rem] py-[0.55rem] transition-[border-color,box-shadow] duration-200 focus-within:border-[color-mix(in_srgb,var(--accent)_55%,var(--hair))] focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_22%,transparent)]",
        className,
      )}
    >
      <span className="inline-flex text-ink-mute" aria-hidden="true">
        {glyph ?? MAGNIFIER}
      </span>
      <input
        className="flex-1 border-none bg-transparent font-mono text-[0.82rem] text-ink outline-none placeholder:text-ink-mute [&::-webkit-search-cancel-button]:hidden"
        type="search"
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
        {...inputProps}
      />
      {value ? (
        <button
          type="button"
          className="cursor-pointer border-none bg-transparent px-[0.2rem] py-[0.1rem] text-[0.7rem] text-ink-mute transition-colors hover:text-ink"
          aria-label={clearAriaLabel}
          onClick={onClear ?? (() => onChange(""))}
        >
          ✕
        </button>
      ) : (
        (hint ?? null)
      )}
    </div>
  )
}
