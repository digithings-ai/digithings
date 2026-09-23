/**
 * TestimonialWall — the trust band promoted from the design reference
 * (layout-patterns/testimonial-wall): a pull-quote wall over a quiet org
 * lockup. Quote data comes in via props; the voice doctrine is the caller's
 * contract — real numbers and real orgs only, phrased as `{Org} × {product}`,
 * never invented. Attribution avatars are mono initials derived from the
 * name; the optional org strip closes the band under a hairline. A quote may
 * carry an `href` so a named customer's org links to its own public site, and
 * `columns` drops the wall to two for a band holding two voices. The quote body
 * accepts a node, so a caller can hand it motion text (`<MotionReveal/>`) that
 * spells the line out on scroll. Entirely
 * token-backed utilities — no family CSS rules. Server component — no state.
 *
 * Wiring (in the consuming app):
 *   globals.css   @source "<path-to>/packages/ui/src/components/data-layout";
 */
import type { ReactNode } from "react";

export type TestimonialQuote = {
  /**
   * The pull-quote itself. A string for plain copy; pass an element instead
   * (e.g. `<MotionReveal text="…" />`) when the quote should spell itself out
   * as it rides up the page. The primitive renders it as-is, so any inline
   * motion text is the caller's choice, not the wall's.
   */
  quote: ReactNode;
  /** Attributed name — initials are derived for the avatar disc. */
  name: string;
  /** Role line — "Systematic PM". */
  role: string;
  /** Organization — pairs with `lockup` as `{org} × {lockup}`. */
  org: string;
  /**
   * Optional public site for the org. When present the org name renders as a
   * link — for a named customer whose site is public, never for a quote whose
   * attribution is only a role.
   */
  href?: string;
};

export type TestimonialWallProps = {
  quotes: TestimonialQuote[];
  /**
   * Columns at the widest breakpoint (collapses to one below 820px). Default
   * 3; use 2 for a wall holding two voices, so the row fills instead of
   * leaving an empty third cell.
   */
  columns?: 2 | 3;
  /** Product half of the `{org} × {product}` lockup; omit to drop it. */
  lockup?: string;
  /** Org names for the quiet strip under the wall; omit to drop the strip. */
  orgs?: string[];
  /** Micro-caps label opening the org strip. */
  orgsLabel?: string;
  /** Accessible name for the org strip — "Illustrative organizations". */
  orgsAriaLabel?: string;
  className?: string;
};

const initials = (name: string) =>
  name
    .split(/[.\s]+/)
    .filter(Boolean)
    .map((p) => p[0])
    .join("");

export function TestimonialWall({
  quotes,
  columns = 3,
  lockup,
  orgs,
  orgsLabel = "trusted by",
  orgsAriaLabel = "Organizations",
  className,
}: TestimonialWallProps) {
  return (
    <div className={className}>
      <div
        className={`grid gap-[0.9rem] max-[820px]:grid-cols-1 ${
          columns === 2 ? "grid-cols-2" : "grid-cols-3"
        }`}
      >
        {quotes.map((q) => (
          <figure
            key={q.name}
            className="m-0 flex flex-col justify-between gap-[1.1rem] rounded-none border border-hair bg-surface p-[1.3rem]"
          >
            <blockquote className="m-0 font-display font-normal text-[1.02rem] leading-[1.4] text-ink">
              {q.quote}
            </blockquote>
            <figcaption className="flex items-center gap-[0.7rem]">
              <span
                className="flex size-[34px] flex-shrink-0 items-center justify-center rounded-none bg-accent-weak font-mono text-[0.62rem] tracking-[0.04em] text-accent"
                aria-hidden="true"
              >
                {initials(q.name)}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="font-mono text-[0.76rem] text-ink">{q.name}</span>
                <span className="font-mono text-[0.62rem] text-ink-mute">
                  {q.role} ·{" "}
                  {q.href ? (
                    <a
                      className="underline-offset-[3px] hover:text-ink hover:underline"
                      href={q.href}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {q.org}
                    </a>
                  ) : (
                    q.org
                  )}
                  {lockup ? <span className="text-accent"> × {lockup}</span> : null}
                </span>
              </span>
            </figcaption>
          </figure>
        ))}
      </div>

      {orgs && orgs.length > 0 ? (
        <div
          className="mt-[1.4rem] flex flex-wrap items-center gap-x-[1.4rem] gap-y-[0.5rem] border-t border-hair pt-[1.1rem] font-mono text-[0.74rem] text-ink-soft"
          aria-label={orgsAriaLabel}
        >
          <span className="text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            {orgsLabel}
          </span>
          {orgs.map((o) => (
            <span key={o}>{o}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
