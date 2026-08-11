"use client";

import { useEffect, useRef } from "react";
import { useInView, useReducedMotion } from "motion/react";

/**
 * Odometer — the mechanical digit-roll counter promoted from the design
 * reference (data/odometer), the companion to the count-up <StatCounter/>.
 * Each digit of a formatted figure is a 0–9 reel that rolls to its value the
 * first time the figure scrolls into view, staggered left to right; non-digit
 * characters ($ , . %) sit static between reels. The figure carries an
 * aria-label so screen readers announce the value once — the reels are
 * decorative.
 *
 * SSR ships every reel already settled on its final digit, so the number is
 * readable with no JS and under reduced motion. When motion is allowed, an
 * effect rewinds the strips to zero (transitions suspended), forces a reflow,
 * and releases them — all imperative DOM writes, no per-frame React state.
 *
 * <OdometerStrip/> is the reference arrangement: a hairline-divided cell grid
 * of labelled odometers (sibling-index hairlines keyed off data-cols in
 * styles/data-layout.css, re-derived for the 2-up collapse below 720px).
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/data-layout.css";
 *                 @source "<path-to>/digiweb/web/src/components/data-layout";
 */
export function Odometer({
  value,
  className,
}: {
  /** Formatted figure — "$1,284,000", "2.31", "98%" … */
  value: string;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { amount: 0.6, once: true });
  const reduced = useReducedMotion();

  // SSR ships the settled reels; once in view (and motion is allowed) rewind
  // every strip to zero with transitions suspended, force a reflow so the
  // rewind commits, then release each reel toward its data-final target.
  useEffect(() => {
    const node = ref.current;
    if (!node || !inView || reduced) return;
    const strips = Array.from(node.querySelectorAll<HTMLElement>(".odo-strip"));
    if (strips.length === 0) return;
    for (const strip of strips) {
      strip.style.transitionProperty = "none";
      strip.style.transform = "translateY(0)";
    }
    void node.offsetHeight; // commit the rewind before the transition re-engages
    for (const strip of strips) {
      strip.style.transitionProperty = "";
      strip.style.transform = strip.dataset.final ?? "";
    }
  }, [inView, reduced]);

  return (
    <span
      ref={ref}
      className={`odo inline-flex items-end font-mono text-[1.7rem] leading-none tabular-nums text-ink${
        className ? ` ${className}` : ""
      }`}
      aria-label={value}
    >
      {value.split("").map((c, i) =>
        /[0-9]/.test(c) ? (
          <span className="inline-block h-[1em] overflow-hidden" key={i} aria-hidden="true">
            <span
              className="odo-strip"
              data-final={`translateY(${-Number(c) * 10}%)`}
              style={{
                transform: `translateY(${-Number(c) * 10}%)`,
                transitionDelay: `${i * 55}ms`,
              }}
            >
              {Array.from({ length: 10 }, (_, n) => (
                <span className="h-[1em] text-center leading-[1em]" key={n}>
                  {n}
                </span>
              ))}
            </span>
          </span>
        ) : (
          <span className="inline-block" key={i} aria-hidden="true">
            {c}
          </span>
        ),
      )}
    </span>
  );
}

export type OdometerStat = {
  /** Formatted figure the reels land on — "$1,284,000", "2.31" … */
  value: string;
  /** Mono micro-caps label under the figure. */
  label: string;
};

const COLS: Record<2 | 3 | 4, string> = {
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

export function OdometerStrip({
  stats,
  columns = 4,
  className,
}: {
  stats: OdometerStat[];
  /** Desktop stats per row (collapses to 2 below 720px). */
  columns?: 2 | 3 | 4;
  className?: string;
}) {
  return (
    <div
      data-cols={columns}
      className={`odo-grid grid ${COLS[columns]} overflow-hidden rounded-[12px] border border-hair bg-surface max-[720px]:grid-cols-2${
        className ? ` ${className}` : ""
      }`}
    >
      {stats.map((s) => (
        <div className="odo-cell p-[1.3rem]" key={s.label}>
          <Odometer value={s.value} />
          <span className="mt-[0.55rem] block font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
            {s.label}
          </span>
        </div>
      ))}
    </div>
  );
}
