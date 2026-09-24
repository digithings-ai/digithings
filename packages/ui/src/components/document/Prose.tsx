import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

/**
 * Long-form prose wrapper (D1, #4429).
 *
 * Caps the measure and sets the loose reading leading, then styles the
 * common inline elements (paragraph rhythm, links, emphasis, lists) so a
 * prose block needs no per-element classes. Accent is furniture only —
 * links and list markers, never body text.
 *
 * Utilities only — no site/app CSS class.
 */
export interface ProseProps {
  children: ReactNode;
  className?: string;
}

export function Prose({ children, className }: ProseProps) {
  return (
    <div
      className={cn(
        "max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft",
        "[&_p]:mt-[1.1em] [&_p:first-child]:mt-0",
        "[&_a]:text-ink [&_a]:underline [&_a]:underline-offset-[3px]",
        "[&_strong]:font-medium [&_strong]:text-ink",
        "[&_em]:italic",
        "[&_ul]:mt-[1.1em] [&_ul]:list-none [&_ul]:p-0 [&_li]:relative [&_li]:pl-[1.4em] [&_li]:leading-[var(--leading-prose)]",
        "[&_li]:before:absolute [&_li]:before:left-0 [&_li]:before:text-ink-mute [&_li]:before:content-['[_*]_']",
        "[&_ol]:mt-[1.1em] [&_ol]:pl-[1.4em] [&_li]:marker:text-ink-mute",
        className,
      )}
    >
      {children}
    </div>
  );
}
