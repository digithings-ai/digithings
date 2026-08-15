"use client";
/**
 * SearchBar — the search field promoted for #1548: a leading glyph, a clear
 * affordance that appears once there's input, and an optional trailing
 * `hint` slot shown while empty (the reference wears a `/` keycap).
 * Controlled — the results pane stays with the caller; the bar only owns
 * the query. Dress lives in styles/controls-core.css (ctl-search / sb-*):
 * focus-within lights the accent ring, and the native WebKit search-cancel
 * affordance is suppressed in favor of the clear button.
 *
 * Shaped against the olympus adoption target: the ticker filter row inside
 * components/portfolio/performance-chart-workspace.tsx's comparables picker.
 */
import type { InputHTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

export type SearchBarProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "value" | "onChange" | "type" | "className"
> & {
  value: string;
  onChange: (query: string) => void;
  /** Clears the query — defaults to onChange(""). */
  onClear?: () => void;
  clearAriaLabel?: string;
  /** Trailing slot shown while the query is empty (keycap hint etc.). */
  hint?: ReactNode;
  /** Replaces the leading magnifier glyph. */
  glyph?: ReactNode;
  /** Lands on the field wrapper, not the input. */
  className?: string;
};

const MAGNIFIER = (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
  </svg>
);

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
    <div data-slot="search-bar" className={cx("ctl-search", className)}>
      <span className="sb-glyph" aria-hidden="true">
        {glyph ?? MAGNIFIER}
      </span>
      <input
        className="sb-input"
        type="search"
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
        {...inputProps}
      />
      {value ? (
        <button
          type="button"
          className="sb-clear"
          aria-label={clearAriaLabel}
          onClick={onClear ?? (() => onChange(""))}
        >
          ✕
        </button>
      ) : (
        (hint ?? null)
      )}
    </div>
  );
}
