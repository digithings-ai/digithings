import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

/**
 * The page opener (D1, #4429).
 *
 * The landing hero's grammar at page-title size: a muted `~/digithings/<path>`
 * line, the title with a blinking block caret, and a one-sentence lede, staged
 * in with `animate-appear` (the kit drops the entrance under reduced motion).
 *
 * Utilities only — no site/app CSS class.
 */
export interface PageTitleProps {
  title: ReactNode;
  /** The page's path under `~/digithings/`, e.g. `services`. */
  path?: string;
  children?: ReactNode;
  className?: string;
}

export function PageTitle({ title, path, children, className }: PageTitleProps) {
  return (
    <header className={cn("max-w-[var(--measure-prose)]", className)}>
      {path ? (
        <p className="animate-appear m-0 mb-[1.1rem] font-mono text-[0.75rem] tracking-[0.04em] text-ink-mute opacity-0">
          {`~/digithings/${path}`}
        </p>
      ) : null}
      <h1 className="animate-appear m-0 font-mono text-[length:var(--type-page-title)] font-medium leading-[1.2] tracking-[-0.02em] text-ink opacity-0 [animation-delay:90ms]">
        {title}
        <span
          aria-hidden="true"
          className="ml-[0.3em] inline-block h-[0.82em] w-[0.5em] bg-accent align-[-0.08em] [animation:chat-cursor-blink_1.1s_steps(1)_infinite] motion-reduce:[animation:none]"
        />
      </h1>
      {children ? (
        <p className="animate-appear mt-[0.9rem] mb-0 text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft opacity-0 [animation-delay:200ms]">
          {children}
        </p>
      ) : null}
    </header>
  );
}
