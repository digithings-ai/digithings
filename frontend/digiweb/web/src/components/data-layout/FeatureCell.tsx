import type { ReactNode } from "react";

/**
 * FeatureCell — the universal feature block promoted from the design reference
 * (layout-patterns/feature-cell), the structure that repeats across graphite /
 * cursor / x.ai and every band we ship: eyebrow → a short outcome headline →
 * one sentence of mechanism → a quiet link → the product visual (children —
 * typically a <ProductFrame/>). Each cell may scope a module livery
 * (`accent-<module>`) that tints the eyebrow and link. Stack cells as direct
 * siblings and even-numbered ones swap copy/visual columns automatically
 * (`:nth-child(even)` in styles/data-layout.css); everything collapses to one
 * column below 760px. Server component — no state, no effects.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/data-layout.css";
 *                 @source "<path-to>/digiweb/web/src/components/data-layout";
 */
export type FeatureCellProps = {
  /** Mono micro-caps eyebrow above the headline — "research". */
  eyebrow: string;
  /** The outcome headline, 4–8 words. */
  outcome: string;
  /** One sentence of mechanism under the headline. */
  mechanism: string;
  /** Destination of the quiet link; omit to drop the link. */
  href?: string;
  /** Link copy. */
  linkLabel?: string;
  /** Optional module livery scope — suffix of an `accent-<module>` class. */
  livery?: string;
  className?: string;
  /** The product visual — typically a <ProductFrame/> crop. */
  children?: ReactNode;
};

export function FeatureCell({
  eyebrow,
  outcome,
  mechanism,
  href,
  linkLabel = "Learn more",
  livery,
  className,
  children,
}: FeatureCellProps) {
  return (
    <article
      className={`fc-cell grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-center gap-[1.6rem] rounded-[12px] border border-hair bg-surface p-[1.6rem] max-[760px]:grid-cols-1${
        livery ? ` accent-${livery}` : ""
      }${className ? ` ${className}` : ""}`}
    >
      <div className="fc-copy">
        <p className="font-mono text-[0.62rem] uppercase tracking-[0.12em] text-accent">
          {eyebrow}
        </p>
        <h3 className="mt-[0.5rem] font-display font-normal text-[clamp(1.3rem,2.6vw,1.7rem)] tracking-[-0.013em] leading-[1.12] text-ink">
          {outcome}
        </h3>
        <p className="mt-[0.6rem] max-w-[42ch] text-[0.92rem] text-ink-soft">{mechanism}</p>
        {href ? (
          <a
            className="fc-link mt-[0.9rem] inline-block font-mono text-[0.72rem] text-accent no-underline"
            href={href}
          >
            {linkLabel} <span aria-hidden="true">→</span>
          </a>
        ) : null}
      </div>
      {children}
    </article>
  );
}
