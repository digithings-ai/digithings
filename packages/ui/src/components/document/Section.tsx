import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

/**
 * A document section (D1, #4429).
 *
 * Sections are separated by a single hairline `border-top` and share one
 * block step (`--page-step`) and one inline inset (`--page-pad`) — never
 * alternating background bands. The first section loses its top border so
 * the header's own hairline is the only line above it.
 *
 * Utilities only — no site/app CSS class.
 */
export interface SectionProps {
  /** Anchor target, when a section is linked to. */
  id?: string;
  /** Section heading; the one h2 at `--type-section`. */
  title?: ReactNode;
  /** One sentence under the heading, at body size and prose leading. */
  lede?: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function Section({ id, title, lede, children, className }: SectionProps) {
  return (
    <section
      id={id}
      className={cn(
        "border-t border-hair px-[var(--page-pad)] py-[var(--page-step)] first:border-t-0",
        className,
      )}
    >
      {title ? (
        <h2 className="m-0 max-w-[var(--measure-prose)] text-[length:var(--type-section)] font-medium leading-[1.35] tracking-[-0.01em] text-ink">
          {title}
        </h2>
      ) : null}
      {lede ? (
        <p className="mt-[0.9rem] mb-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
          {lede}
        </p>
      ) : null}
      {children ? (
        <div className={cn(title || lede ? "mt-[1.6rem]" : undefined)}>{children}</div>
      ) : null}
    </section>
  );
}
