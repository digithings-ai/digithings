/**
 * Breadcrumb — the wayfinding trail (`nav[aria-label] > ol`), promoted from the
 * controls layer into the kit (#4306, batch K2). Items are `{ label, href }`;
 * the last item without an `href` renders as the current page
 * (`aria-current="page"`, not a link). Separators are `/` spans, `aria-hidden`.
 *
 * The `.ctl-crumbs*` dress is translated into token utilities here, so the
 * controls CSS can retire. Prose, not controls: the trail is a navigation
 * landmark, and each link is a pointer affordance with the canon focus ring.
 */

import type { ReactNode } from "react"

import { cn } from "../lib/utils"

export type Crumb = {
  label: ReactNode
  href?: string
}

export type BreadcrumbProps = {
  items: Crumb[]
  ariaLabel?: string
  className?: string
}

export function Breadcrumbs({ items, ariaLabel = "Breadcrumb", className }: BreadcrumbProps) {
  return (
    <nav aria-label={ariaLabel} data-slot="breadcrumbs" className={className}>
      <ol className="m-0 flex list-none flex-wrap items-baseline gap-[0.45rem] p-0 font-mono text-[0.78rem]">
        {items.map((item, i) => {
          const isLast = i === items.length - 1
          const isCurrent = isLast && item.href == null
          return (
            <li key={i} className="inline-flex min-w-0 items-baseline gap-[0.45rem]">
              {i > 0 ? (
                <span aria-hidden="true" className="text-ink-mute">
                  /
                </span>
              ) : null}
              {isCurrent ? (
                <span aria-current="page" className="text-ink">
                  {item.label}
                </span>
              ) : item.href != null ? (
                <a
                  href={item.href}
                  className="cursor-pointer text-ink-soft no-underline transition-colors hover:text-ink focus-visible:text-ink focus-visible:ring-[3px] focus-visible:ring-accent/30 focus-visible:outline-none"
                >
                  {item.label}
                </a>
              ) : (
                <span className="text-ink-soft">{item.label}</span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
