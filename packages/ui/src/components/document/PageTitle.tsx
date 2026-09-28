import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

/**
 * The page opener (D1, #4429).
 *
 * A page title and a one-sentence lede — no eyebrow kicker, no display
 * hero. The title sits at `--type-page-title`; the lede is a single
 * sentence at prose leading.
 *
 * Utilities only — no site/app CSS class.
 */
export interface PageTitleProps {
  title: ReactNode;
  children?: ReactNode;
  className?: string;
}

export function PageTitle({ title, children, className }: PageTitleProps) {
  return (
    <header className={cn("max-w-[var(--measure-prose)]", className)}>
      <h1 className="m-0 font-mono text-[length:var(--type-page-title)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
        {title}
      </h1>
      {children ? (
        <p className="mt-[0.9rem] mb-0 text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft">
          {children}
        </p>
      ) : null}
    </header>
  );
}
