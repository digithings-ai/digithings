"use client"

/**
 * IconButton — the borderless 2rem glyph button (#1548), promoted from the
 * controls layer into the kit (#4306, batch K1). `aria-label` is required —
 * the child is a bare svg. Ink-mute glyph, ink + ink/6 wash on hover, the
 * kit's not-allowed disabled convention, and a token-backed focus ring.
 * Token utilities only, so `.nb-icon` can retire.
 *
 * A plain `<button>` (not the Base UI Button primitive): the controls part was
 * plain, and Base UI re-emits `disabled`/`aria-disabled` in its own attribute
 * order — a real dashboard specimen asserts on that order, and the plain
 * element keeps the rendered markup byte-for-byte compatible.
 */

import type { ComponentPropsWithoutRef } from "react"

import { cn } from "../lib/utils"

export type IconButtonProps = ComponentPropsWithoutRef<"button"> & {
  "aria-label": string
}

export function IconButton({ className, ...props }: IconButtonProps) {
  return (
    <button
      type="button"
      data-slot="icon-button"
      className={cn(
        "inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-none border-0 bg-transparent text-ink-mute transition-colors outline-none hover:bg-ink/6 hover:text-ink focus-visible:ring-1 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    />
  )
}
