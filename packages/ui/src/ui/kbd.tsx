import type { HTMLAttributes } from "react"
import { cn } from "../lib/utils"

/**
 * Kbd — the keycap chip. Promoted from the reference gallery's global `.kbd`
 * (apps/reference/app/globals.css), which was reference-only: an app that
 * wanted a keycap had no canonical part to reach for and would have tripped
 * the family census.
 *
 * The keycap look: hairline box, a heavier bottom border so it reads as a
 * physical key, the ink-wash fill, mono at the micro size. Token utilities
 * only — no app-local class family. Renders a real `<kbd>`, so the phase-id /
 * shortcut chips it dresses keep their semantic.
 */
export type KbdProps = HTMLAttributes<HTMLElement>

function Kbd({ className, children, ...props }: KbdProps) {
  return (
    <kbd
      className={cn(
        "inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded-none border border-hair border-b-2 bg-ink/5 px-[0.3rem] align-middle font-mono text-[0.62rem] leading-none text-ink-soft",
        className,
      )}
      {...props}
    >
      {children}
    </kbd>
  )
}

export { Kbd }
