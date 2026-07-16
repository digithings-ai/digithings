"use client";
/**
 * NavButtons — the wayfinding controls promoted for #1548. Pills for chrome,
 * hairline for structure — one loud state per group:
 *
 * - SegmentedControl: the range switch (nb-seg / nb-seg-group). Plain
 *   buttons wearing aria-pressed inside a role="group" — deliberately NOT
 *   tablist (the semantics the reference specimen and olympus
 *   performance-date-range.tsx previously misused): the segments switch a
 *   data range on the same view, they don't own tab panels.
 * - Pager: prev/next with disabled edge states (nb-page-edge) around a
 *   middle slot — numbered PagerPage cells (aria-current="page") or any
 *   label (olympus PipelineDaySelector keeps its date label between the
 *   chevrons).
 * - IconButton: the borderless 2rem glyph button (nb-icon); aria-label is
 *   required — the child is a bare svg.
 *
 * Dress lives in styles/controls-core.css, state keyed off aria attributes.
 *
 * Shaped against the olympus adoption targets:
 * components/portfolio/performance-date-range.tsx (segmented ITD/YTD/3M/1M)
 * and components/pipeline/PipelineDaySelector.tsx (prev/next day pager).
 */
import type { ComponentPropsWithoutRef, HTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

export type SegmentedOption<T extends string = string> = {
  value: T;
  /** Defaults to the value itself. */
  label?: ReactNode;
  disabled?: boolean;
};

export type SegmentedControlProps<T extends string = string> = Omit<
  HTMLAttributes<HTMLDivElement>,
  "onChange"
> & {
  options: ReadonlyArray<T | SegmentedOption<T>>;
  value: T;
  onChange?: (value: T) => void;
};

export function SegmentedControl<T extends string = string>({
  options,
  value,
  onChange,
  className,
  ...props
}: SegmentedControlProps<T>) {
  return (
    <div data-slot="segmented" role="group" className={cx("nb-seg-group", className)} {...props}>
      {options.map((option) => {
        const opt = typeof option === "string" ? { value: option } : option;
        return (
          <button
            key={opt.value}
            type="button"
            className="nb-seg"
            aria-pressed={opt.value === value}
            disabled={opt.disabled}
            onClick={() => onChange?.(opt.value)}
          >
            {opt.label ?? opt.value}
          </button>
        );
      })}
    </div>
  );
}

export type PagerProps = HTMLAttributes<HTMLDivElement> & {
  onPrev?: () => void;
  onNext?: () => void;
  prevDisabled?: boolean;
  nextDisabled?: boolean;
  prevLabel?: ReactNode;
  nextLabel?: ReactNode;
  /** Set these when the edge labels are bare glyphs (chevrons). */
  prevAriaLabel?: string;
  nextAriaLabel?: string;
  /** Middle slot — PagerPage cells, or any label (a date, "3 / 12", …). */
  children?: ReactNode;
};

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
  ...props
}: PagerProps) {
  return (
    <div data-slot="pager" className={cx("nb-pager", className)} {...props}>
      <button
        type="button"
        className="nb-page-edge"
        disabled={prevDisabled}
        aria-label={prevAriaLabel}
        onClick={onPrev}
      >
        {prevLabel}
      </button>
      {children}
      <button
        type="button"
        className="nb-page-edge"
        disabled={nextDisabled}
        aria-label={nextAriaLabel}
        onClick={onNext}
      >
        {nextLabel}
      </button>
    </div>
  );
}

export type PagerPageProps = ComponentPropsWithoutRef<"button"> & {
  /** The current page — wears the accent fill and aria-current="page". */
  current?: boolean;
};

export function PagerPage({ current, className, ...props }: PagerPageProps) {
  return (
    <button
      type="button"
      data-slot="pager-page"
      className={cx("nb-page", className)}
      aria-current={current ? "page" : undefined}
      {...props}
    />
  );
}

export type IconButtonProps = ComponentPropsWithoutRef<"button"> & {
  "aria-label": string;
};

export function IconButton({ className, ...props }: IconButtonProps) {
  return <button type="button" data-slot="icon-button" className={cx("nb-icon", className)} {...props} />;
}
