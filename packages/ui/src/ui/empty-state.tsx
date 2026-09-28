"use client"

/**
 * EmptyState — the no-results / first-run / load-error triple (#1548),
 * promoted from the controls layer into the kit (#4306, batch K1). A centered
 * hairline card: glyph disc, mono title, one line of guidance, and the single
 * action that moves the user forward. Monochrome by default; `variant="error"`
 * is the only one that spends the down/danger color (on the glyph disc).
 *
 * The old `.ctl-empty*` dress (styles/controls-core.css) is translated
 * value-for-value into token utilities here, so the controls CSS can retire.
 * The `glass` / `glass-display` dresses restyle type/spacing/slots ONLY — the
 * surface class stays call-site (dashboard's `.glass-card`) so the app's
 * motion-reveal hook keeps firing.
 *
 * #4452: `glass-display` is the full-page gate card (dashboard's DB gate) and
 * must survive phone widths. It is declared `w-full` (fluid: fills its
 * container up to a consumer cap, never content-sized) and its title/body
 * `break-words` (a long unbreakable token breaks rather than overflowing).
 * The dress is text-first, so it may never ellipsise its own message:
 * `truncate` / `whitespace-nowrap` / `line-clamp` are banned here.
 */

import type { HTMLAttributes, ReactNode } from "react"

import { cn } from "../lib/utils"

export type EmptyStateVariant = "no-results" | "first-run" | "error"

export type EmptyStateDress = "reference" | "glass" | "glass-display"

export type EmptyStateProps = Omit<HTMLAttributes<HTMLElement>, "title"> & {
  variant?: EmptyStateVariant
  /** Look cut — "reference" (default) or the dashboard glass cuts (see docblock). */
  dress?: EmptyStateDress
  /** Replaces the variant's default glyph inside the disc. */
  icon?: ReactNode
  title: ReactNode
  /** One line of guidance under the title. */
  body?: ReactNode
  /** Short italic secondary line — explains *why* it's empty without reading as broken. */
  note?: ReactNode
  /** The single action that moves forward — pass a `<Button/>`. */
  action?: ReactNode
}

const DEFAULT_GLYPHS: Record<EmptyStateVariant, ReactNode> = {
  "no-results": (
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5M8 11h6" strokeLinecap="round" />
    </>
  ),
  "first-run": (
    <>
      <path d="M12 3v18M3 12h18" strokeLinecap="round" />
      <circle cx="12" cy="12" r="9" opacity="0.35" />
    </>
  ),
  error: (
    <>
      <path d="M12 3l9 16H3z" />
      <path d="M12 10v4M12 17v.5" strokeLinecap="round" />
    </>
  ),
}

export function EmptyState({
  variant = "no-results",
  dress = "reference",
  icon,
  title,
  body,
  note,
  action,
  className,
  children,
  ...props
}: EmptyStateProps) {
  // The dashboard glass dresses ship without a glyph disc; an explicit `icon`
  // still renders one. The reference dress always wears its variant glyph.
  const glyphless = dress !== "reference" && icon == null
  // WCAG 4.1.3 (#2287): "error" is the one variant that can appear or replace
  // prior content asynchronously — give it an assertive live role. Spread
  // AFTER ...props so the derived role stays authoritative.
  const live = variant === "error" ? ({ role: "alert" as const }) : {}
  const glass = dress === "glass"
  const glassDisplay = dress === "glass-display"
  return (
    <article
      data-slot="empty-state"
      className={cn(
        "flex flex-col items-center border border-hair bg-surface/55 p-[1.8rem_1.3rem] text-center",
        // glass: justify-center gap-2 p-8 (observability quiet card)
        glass && "justify-center gap-2 p-8",
        // glass-display: w-full justify-center gap-0 px-6 py-8 (full-page gate
        // card). #4452: `w-full` states the fluid contract explicitly — the card
        // fills its container up to any consumer `max-w-*`, so it can never be
        // content-sized past the viewport.
        glassDisplay && "w-full justify-center gap-0 px-6 py-8",
        !glass && !glassDisplay && "gap-[0.55rem]",
        className,
      )}
      {...props}
      {...live}
    >
      {glyphless ? null : (
        <span
          className={cn(
            "mb-[0.15rem] grid size-11 place-items-center rounded-full bg-ink/8 text-ink-mute",
            variant === "error" && "bg-danger/12 text-danger",
          )}
          aria-hidden="true"
        >
          {icon ?? (
            <svg
              viewBox="0 0 24 24"
              width="22"
              height="22"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            >
              {DEFAULT_GLYPHS[variant]}
            </svg>
          )}
        </span>
      )}
      <h3
        className={cn(
          "m-0 font-mono text-[0.86rem] font-normal text-ink",
          glass && "font-sans text-sm leading-[1.4286] font-medium text-ink-soft",
          glassDisplay && "font-display break-words text-2xl leading-[1.3333] tracking-tight font-normal text-ink",
        )}
      >
        {title}
      </h3>
      {body != null ? (
        <p
          className={cn(
            "max-w-[24ch] text-[0.8rem] leading-[1.5] text-ink-mute",
            !glass && !glassDisplay && "mt-0 mb-[0.4rem]",
            glass && "m-0 max-w-md text-xs leading-[1.3333]",
            glassDisplay && "mt-2 mb-0 max-w-none break-words text-sm leading-[1.625]",
          )}
        >
          {body}
        </p>
      ) : null}
      {note != null ? (
        <p
          className={cn(
            "m-0 max-w-[24ch] text-[0.75rem] leading-[1.3333] italic text-ink-mute/60",
            glass && "mt-1 max-w-md",
          )}
        >
          {note}
        </p>
      ) : null}
      {action}
      {children}
    </article>
  )
}
