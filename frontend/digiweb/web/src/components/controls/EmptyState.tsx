/**
 * EmptyState — the no-results / first-run / load-error triple promoted for
 * #1548: the outcomes a skeleton loader resolves into when there's nothing
 * to show. A centered hairline card — glyph disc, mono title, one line of
 * guidance, and the single action that moves the user forward. Monochrome
 * by default; variant="error" is the only one that spends the down color
 * (on the glyph disc). Each variant ships a default glyph; the `icon` slot
 * replaces it. Dress lives in styles/controls-core.css (ctl-empty*).
 *
 * Shaped against the olympus adoption targets:
 * components/observability/shared.tsx EmptyState (title/message/note),
 * components/db-unavailable.tsx (title/body/Retry action), and the inline
 * "No matches" / "No runs recorded yet" strings.
 */
import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

export type EmptyStateVariant = "no-results" | "first-run" | "error";

export type EmptyStateProps = Omit<HTMLAttributes<HTMLElement>, "title"> & {
  variant?: EmptyStateVariant;
  /** Replaces the variant's default glyph inside the disc. */
  icon?: ReactNode;
  title: ReactNode;
  /** One line of guidance under the title. */
  body?: ReactNode;
  /** The single action that moves forward — pass a `<Button/>`. */
  action?: ReactNode;
};

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
};

export function EmptyState({
  variant = "no-results",
  icon,
  title,
  body,
  action,
  className,
  children,
  ...props
}: EmptyStateProps) {
  return (
    <article
      data-slot="empty-state"
      className={cx("ctl-empty", variant === "error" && "ctl-empty--error", className)}
      {...props}
    >
      <span className="ctl-empty-glyph" aria-hidden="true">
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
      <h3 className="ctl-empty-title">{title}</h3>
      {body != null ? <p className="ctl-empty-body">{body}</p> : null}
      {action}
      {children}
    </article>
  );
}
