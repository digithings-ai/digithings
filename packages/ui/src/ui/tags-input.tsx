"use client"
/**
 * TagsInput — the chips multi-select, promoted from the controls layer into
 * the kit (#4306, batch K2). Controlled: the caller owns the tag list, the
 * field owns the draft. Enter (or comma) commits the trimmed draft, Backspace
 * on an empty draft removes the last chip, every chip carries its own ×
 * remove, clicking anywhere in the field focuses the input. Duplicates are
 * dropped before `onAdd` fires. Optional `suggestions` render as +chips below
 * the field (already-added values are filtered out).
 *
 * The `.tg-*` dress is translated into token utilities here (logical
 * padding, so chips mirror under RTL); the chipless-input stretch is the
 * field's `:first-child` rule. The dashboard's deferred quant-chip dress is
 * not carried — no live consumer passes it.
 */
import { useRef, useState } from "react"
import type { HTMLAttributes, KeyboardEvent, MouseEvent, ReactNode } from "react"

import { cn } from "../lib/utils"

export type TagChipProps = {
  label: ReactNode
  /** Renders the × remove control when present. */
  onRemove?: () => void
  removeAriaLabel?: string
  className?: string
}

export function TagChip({ label, onRemove, removeAriaLabel, className }: TagChipProps) {
  return (
    <span
      data-slot="tag-chip"
      className={cn(
        "inline-flex items-center gap-[0.35rem] border border-[color-mix(in_srgb,var(--accent)_32%,var(--hair))] bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] ps-[0.6rem] pe-[0.35rem] py-[0.22rem] font-mono text-[0.74rem] whitespace-nowrap text-ink",
        className,
      )}
    >
      {label}
      {onRemove ? (
        <button
          type="button"
          className="inline-flex cursor-pointer items-center justify-center rounded-none border-none bg-transparent p-[0.1rem] text-ink-mute transition-colors duration-150 hover:text-ink"
          aria-label={removeAriaLabel ?? "Remove"}
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
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
  )
}

export type TagsInputProps = Omit<HTMLAttributes<HTMLDivElement>, "onChange"> & {
  /** The chips — caller-owned. */
  value: string[]
  /** A trimmed, dedup-checked tag was committed (Enter/comma/suggestion). */
  onAdd?: (tag: string) => void
  /** A chip's × was clicked, or Backspace fired on an empty draft. */
  onRemove?: (tag: string, index: number) => void
  /** Shown only while the field is chipless (the reference behavior). */
  placeholder?: string
  inputAriaLabel?: string
  /** +chips below the field; values already in `value` are filtered out. */
  suggestions?: string[]
  suggestionsLabel?: string
  disabled?: boolean
}

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
  const [draft, setDraft] = useState("")
  const inputRef = useRef<HTMLInputElement | null>(null)

  const add = (raw: string) => {
    const tag = raw.trim().replace(/,$/, "")
    if (tag && !value.includes(tag)) onAdd?.(tag)
    setDraft("")
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      add(draft)
    } else if (e.key === "Backspace" && draft === "" && value.length) {
      onRemove?.(value[value.length - 1], value.length - 1)
    }
  }

  const remaining = (suggestions ?? []).filter((s) => !value.includes(s))

  return (
    <>
      <div
        data-slot="tags-input"
        className={cn(
          "flex w-[min(100%,30rem)] cursor-text flex-wrap items-center gap-[0.4rem] border border-hair bg-surface px-[0.6rem] py-[0.5rem] transition-[border-color,box-shadow] duration-200 focus-within:border-[color-mix(in_srgb,var(--accent)_55%,var(--hair))] focus-within:shadow-[0_0_0_3px_color-mix(in_srgb,var(--accent)_20%,transparent)]",
          className,
        )}
        onClick={(e: MouseEvent<HTMLDivElement>) => {
          inputRef.current?.focus()
          onClick?.(e)
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
          className="min-w-[7rem] border-none bg-transparent p-[0.2rem] font-mono text-[0.8rem] text-ink outline-none first:flex-1 placeholder:text-ink-mute"
          value={draft}
          placeholder={value.length ? "" : placeholder}
          aria-label={inputAriaLabel}
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>
      {remaining.length ? (
        <div data-slot="tag-suggestions" className="mt-[0.7rem] flex flex-wrap items-center gap-[0.4rem]">
          <span className="me-[0.2rem] font-mono text-[0.56rem] tracking-[0.1em] text-ink-mute uppercase">
            {suggestionsLabel}
          </span>
          {remaining.map((s) => (
            <button
              key={s}
              type="button"
              className="cursor-pointer border border-hair bg-transparent px-[0.6rem] py-[0.25rem] font-mono text-[0.72rem] text-ink-soft transition-colors duration-150 hover:border-[color-mix(in_srgb,var(--accent)_45%,var(--hair))] hover:text-ink disabled:cursor-not-allowed"
              disabled={disabled}
              onClick={() => add(s)}
            >
              + {s}
            </button>
          ))}
        </div>
      ) : null}
    </>
  )
}
