import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

/**
 * Figure — the numbered `Fig N` figure grammar (D1, #4429): a `<figure>` whose
 * content (a metric strip, a media block, a diagram) carries a mono
 * `<figcaption>` that leads with `Fig <n>` in the accent tone. The opencode.ai
 * language numbers its stat blocks this way, and both the landing metrics band
 * and the quality page's counted figures use it.
 *
 * Generic on purpose: pass any content as `children`, the caption as `caption`,
 * and the number/label as `n` (`1`, `2`, `"3a"` …). `n` is caller-controlled
 * rather than auto-sequenced so a page can keep its own order explicit.
 *
 * Server component — no hooks, no state.
 */
export type FigureProps = {
  /** The label rendered as `Fig <n>`. Caller-ordered. */
  n: number | string;
  /** The caption text after the `Fig <n>` label. */
  caption: ReactNode;
  /** The figure content — a stat strip, media block, diagram … */
  children: ReactNode;
  className?: string;
};

export function Figure({ n, caption, children, className }: FigureProps) {
  return (
    <figure className={cn("m-0 grid gap-[0.7rem]", className)}>
      {children}
      <figcaption className="font-mono text-[0.72rem] leading-[1.5] text-ink-mute">
        <span className="text-accent">Fig {n}</span>
        <span aria-hidden="true"> — </span>
        {caption}
      </figcaption>
    </figure>
  );
}
