import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

/**
 * The glyph list (D1, #4429).
 *
 * One list grammar for the whole site: a muted `[*]` marker, then a bold
 * lead-in and one unpunctuated clause. No borders, no bullets, no
 * description columns — the list reads as a dense block of statements.
 *
 * Utilities only — no site/app CSS class.
 */
export interface GlyphListProps {
  children: ReactNode;
  className?: string;
}

export function GlyphList({ children, className }: GlyphListProps) {
  return (
    <ul className={cn("m-0 grid list-none gap-[1rem] p-0", className)}>{children}</ul>
  );
}

export interface GlyphRowProps {
  /** The bold lead-in; rendered in ink at medium weight. */
  label?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function GlyphRow({ label, children, className }: GlyphRowProps) {
  return (
    <li
      className={cn(
        "flex gap-[0.75rem] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft",
        className,
      )}
    >
      <span aria-hidden="true" className="shrink-0 font-mono text-ink-mute">
        [*]
      </span>
      <span>
        {label ? (
          <strong className="mr-[0.6rem] font-medium text-ink">{label}</strong>
        ) : null}
        {children}
      </span>
    </li>
  );
}
