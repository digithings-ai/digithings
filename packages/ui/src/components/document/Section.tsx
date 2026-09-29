import type { ReactNode } from "react";

import { cn } from "../../lib/utils";
import { Reveal } from "../../motion/primitives";

/**
 * A document section (D1, #4429).
 *
 * A full-bleed hairline on top — it crosses the page rails, as the landing
 * bands' rules do — then one inline inset (`--page-pad`) and a block step
 * tighter than the landing's `--page-step`, because a document section is a
 * few rows rather than a band. Headings number themselves `// 01`, `// 02`
 * from the frame's counter. The content rises in once when scrolled into view.
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
        "relative px-[var(--page-pad)] py-[clamp(3rem,6vw,5rem)]",
        "before:pointer-events-none before:absolute before:top-0 before:left-1/2 before:h-px before:w-screen before:-translate-x-1/2 before:bg-hair",
        className,
      )}
    >
      <Reveal>
        {title ? (
          <h2 className="m-0 max-w-[var(--measure-prose)] text-[length:var(--type-section)] font-medium leading-[1.35] tracking-[-0.01em] text-ink [counter-increment:doc-section] before:mb-[0.8rem] before:block before:font-mono before:text-[0.72rem] before:font-normal before:tracking-[0.04em] before:text-ink-mute before:content-['//_'_counter(doc-section,decimal-leading-zero)]">
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
      </Reveal>
    </section>
  );
}
