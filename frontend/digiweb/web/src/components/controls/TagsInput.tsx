"use client";
/**
 * TagsInput — the chips multi-select promoted for #1548. Controlled: the
 * caller owns the tag list, the field owns the draft. Enter (or comma)
 * commits the trimmed draft, Backspace on an empty draft removes the last
 * chip, every chip carries its own × remove, clicking anywhere in the field
 * focuses the input. Duplicates are dropped before onAdd fires. Optional
 * `suggestions` render as +chips below the field (already-added values are
 * filtered out). Dress lives in styles/controls-core.css (tg-*): the field
 * lights the accent on focus-within, and the input stretches to the full
 * row only while the field is chipless.
 *
 * Shaped against the olympus adoption target: the NAV-comparables picker in
 * components/portfolio/performance-chart-workspace.tsx (chips with remove,
 * filter-as-you-type, capped multi-select, outside-click dismissal — the
 * pane/dismissal stays caller-side; the chips row + filter input is this).
 */
import { useRef, useState } from "react";
import type { HTMLAttributes, KeyboardEvent, MouseEvent, ReactNode } from "react";

import { cx } from "./cx";

export type TagChipProps = {
  label: ReactNode;
  /** Renders the × remove control when present. */
  onRemove?: () => void;
  removeAriaLabel?: string;
  className?: string;
};

export function TagChip({ label, onRemove, removeAriaLabel, className }: TagChipProps) {
  return (
    <span data-slot="tag-chip" className={cx("tg-chip", className)}>
      {label}
      {onRemove ? (
        <button
          type="button"
          className="tg-x"
          aria-label={removeAriaLabel ?? "Remove"}
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
        >
          <svg
            viewBox="0 0 24 24"
            width="11"
            height="11"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      ) : null}
    </span>
  );
}

export type TagsInputProps = Omit<HTMLAttributes<HTMLDivElement>, "onChange"> & {
  /** The chips — caller-owned. */
  value: string[];
  /** A trimmed, dedup-checked tag was committed (Enter/comma/suggestion). */
  onAdd?: (tag: string) => void;
  /** A chip's × was clicked, or Backspace fired on an empty draft. */
  onRemove?: (tag: string, index: number) => void;
  /** Shown only while the field is chipless (the reference behavior). */
  placeholder?: string;
  inputAriaLabel?: string;
  /** +chips below the field; values already in `value` are filtered out. */
  suggestions?: string[];
  suggestionsLabel?: string;
  disabled?: boolean;
};

export function TagsInput({
  value,
  onAdd,
  onRemove,
  placeholder,
  inputAriaLabel = "Add a tag",
  suggestions,
  suggestionsLabel = "suggestions",
  disabled,
  className,
  onClick,
  ...props
}: TagsInputProps) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const add = (raw: string) => {
    const tag = raw.trim().replace(/,$/, "");
    if (tag && !value.includes(tag)) onAdd?.(tag);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && draft === "" && value.length) {
      onRemove?.(value[value.length - 1], value.length - 1);
    }
  };

  const remaining = (suggestions ?? []).filter((s) => !value.includes(s));

  return (
    <>
      <div
        data-slot="tags-input"
        className={cx("tg-field", className)}
        onClick={(e: MouseEvent<HTMLDivElement>) => {
          inputRef.current?.focus();
          onClick?.(e);
        }}
        {...props}
      >
        {value.map((tag, i) => (
          <TagChip
            key={tag}
            label={tag}
            removeAriaLabel={`Remove ${tag}`}
            onRemove={disabled ? undefined : () => onRemove?.(tag, i)}
          />
        ))}
        <input
          ref={inputRef}
          className="tg-input"
          value={draft}
          placeholder={value.length ? "" : placeholder}
          aria-label={inputAriaLabel}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>
      {remaining.length ? (
        <div data-slot="tag-suggestions" className="tg-suggest-row">
          <span className="tg-suggest-label">{suggestionsLabel}</span>
          {remaining.map((s) => (
            <button
              key={s}
              type="button"
              className="tg-suggest-chip"
              disabled={disabled}
              onClick={() => add(s)}
            >
              + {s}
            </button>
          ))}
        </div>
      ) : null}
    </>
  );
}
