/**
 * Pagination — the numbered page trail (`nav[aria-label]`), promoted from the
 * controls layer into the kit (#4306, batch K2). Controlled: `page` (1-based)
 * + `pageCount`, with either `hrefForPage` (links) or `onPageChange` (buttons).
 * The window shows first / last with an ellipsis around the current page;
 * prev/next disable at the edges. The current page is the one loud control
 * (ink fill); siblings are hairline ghosts.
 *
 * The `.ctl-pagination*` dress is translated into token utilities here, so the
 * controls CSS can retire. Direction glyphs mirror under RTL via `rtl:`.
 */

import { cn } from "../lib/utils"

export type PaginationProps = {
  page: number
  pageCount: number
  onPageChange?: (page: number) => void
  hrefForPage?: (page: number) => string
  ariaLabel?: string
  className?: string
}

/** 1-based page window: first, last, and ±1 around current, ellipsis-filled. */
export function paginationWindow(page: number, pageCount: number): (number | "…")[] {
  const pages = new Set<number>([1, pageCount, page - 1, page, page + 1])
  const sorted = [...pages].filter((p) => p >= 1 && p <= pageCount).sort((a, b) => a - b)
  const out: (number | "…")[] = []
  for (const p of sorted) {
    if (out.length > 0 && p - (out[out.length - 1] as number) > 1) out.push("…")
    out.push(p)
  }
  return out
}

const ITEM =
  "inline-flex h-[2rem] min-w-[2rem] items-center justify-center border border-hair bg-transparent px-[0.5rem] text-ink-soft no-underline transition-colors [font:inherit] hover:border-hair-2 hover:text-ink focus-visible:border-hair-2 focus-visible:ring-[3px] focus-visible:ring-accent/30 focus-visible:outline-none"

export function Pagination({
  page,
  pageCount,
  onPageChange,
  hrefForPage,
  ariaLabel = "Pagination",
  className,
}: PaginationProps) {
  if (pageCount < 1) return null
  const current = Math.max(1, Math.min(pageCount, Math.floor(page)))
  const go = (p: number) => onPageChange?.(Math.max(1, Math.min(pageCount, p)))

  const item = (p: number) => {
    const isCurrent = p === current
    const cls = cn(ITEM, isCurrent && "cursor-default border-ink bg-ink font-semibold text-bg")
    const inner = String(p)
    if (isCurrent) {
      return (
        <span key={p} aria-current="page" className={cls}>
          {inner}
        </span>
      )
    }
    if (hrefForPage) {
      return (
        <a key={p} href={hrefForPage(p)} className={cn(ITEM, "cursor-pointer")}>
          {inner}
        </a>
      )
    }
    return (
      <button key={p} type="button" className={cn(ITEM, "cursor-pointer")} onClick={() => go(p)}>
        {inner}
      </button>
    )
  }

  const step = (dir: -1 | 1) => {
    const target = current + dir
    const disabled = dir === -1 ? current <= 1 : current >= pageCount
    const label = dir === -1 ? "Previous page" : "Next page"
    const glyph = dir === -1 ? "←" : "→"
    const cls = cn(ITEM, "cursor-pointer disabled:cursor-not-allowed disabled:opacity-40")
    if (hrefForPage && !disabled) {
      return (
        <a key={dir} href={hrefForPage(target)} aria-label={label} className={cls}>
          <span aria-hidden="true" className="inline-block rtl:scale-x-[-1]">
            {glyph}
          </span>
        </a>
      )
    }
    return (
      <button
        key={dir}
        type="button"
        aria-label={label}
        className={cls}
        disabled={disabled}
        onClick={() => go(target)}
      >
        <span aria-hidden="true" className="inline-block rtl:scale-x-[-1]">
          {glyph}
        </span>
      </button>
    )
  }

  return (
    <nav
      aria-label={ariaLabel}
      data-slot="pagination"
      className={cn("flex items-center gap-[0.4rem] font-mono text-[0.8rem]", className)}
    >
      {step(-1)}
      {paginationWindow(current, pageCount).map((p, i) =>
        p === "…" ? (
          <span key={`gap-${i}`} aria-hidden="true" className="px-[0.1rem] text-ink-mute">
            …
          </span>
        ) : (
          item(p)
        ),
      )}
      {step(1)}
    </nav>
  )
}
