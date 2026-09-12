"use client";
import { m, useMotionSafe, EASE } from "../../motion/primitives";

/**
 * NumberedStages — the sequential-stage grammar promoted from the design
 * reference (layout-patterns/numbered-stages): a numbered spine where each
 * step is one move in the flow — big mono index badge, an optional mono
 * micro-caps tag, a serif title, one sentence of mechanism. A hairline spine
 * (`.ns-stage::before`, styles/stages.css) runs through the badge column and
 * stops at the last stage; each stage may scope its own module livery via
 * `livery` (`accent-<module>` — declared in @digithings/design/tokens.css),
 * which re-tints the badge's two-color color-mix and the tag/index text.
 *
 * Scroll cadence (#1450): stages fill the pipeline one at a time — each row
 * rises in on its own whileInView with an index-staggered delay, so on a
 * normal scroll the spine reads 01 → 02 → 03 → 04 in order. `animated={false}`
 * opts a consumer out; reduced motion (useMotionSafe) and no-JS
 * (html.no-js [data-motion]) render every stage visible with no animation.
 *
 * Alignment: the badge pill is 2rem tall; an untagged title's first line is
 * flex-centered against that height so pill and title read as one row. With a
 * `tag`, the tag takes the pill-aligned slot and the title stacks under it.
 *
 * Client component (Motion m.li under the app's MotionProvider). Wiring (in
 * the consuming app):
 *   globals.css   @import "@digithings/web/styles/stages.css";
 *                 @source "<path-to>/digiweb/web/src/components/stages";
 */
export type NumberedStage = {
  /** Big mono index rendered in the spine badge — "1.0", "01", "a" … */
  num: string;
  /** Serif stage title. */
  title: string;
  /** One sentence of mechanism under the title. */
  mech: string;
  /** Optional mono micro-caps tag above the title (module name, phase …). */
  tag?: string;
  /** Optional module livery scope — suffix of an `accent-<module>` class. */
  livery?: string;
};

export function NumberedStages({
  stages,
  className,
  animated = true,
}: {
  stages: NumberedStage[];
  className?: string;
  /** Sequential scroll fill (default). Pass false for a static spine. */
  animated?: boolean;
}) {
  const safe = useMotionSafe();
  const fill = animated && safe;

  return (
    <ol className={["grid list-none gap-0 p-0", className].filter(Boolean).join(" ")}>
      {stages.map((s, i) => {
        // Utilities live in clean string literals on purpose: a template hole
        // butted against a candidate (`pb-[…]${`) hides it from Tailwind's
        // scanner, so the utility is silently never generated — the original
        // pb-[1.8rem] shipped un-compiled and the stages rendered with no
        // inter-stage padding at all (#1450 round 3). 2.8rem is the ruled
        // breathing room between a stage's blurb and the next stage's title;
        // the spine ::before spans the padded box (styles/stages.css), so the
        // connector stays continuous, and :last-child zeroes the trailing pad.
        const liClass = [
          "ns-stage relative grid grid-cols-[3.4rem_1fr] gap-[1.1rem] pb-[2.8rem]",
          s.livery ? `accent-${s.livery}` : "",
        ]
          .filter(Boolean)
          .join(" ");
        const content = (
          <>
            <span className="ns-node" aria-hidden="true">
              {s.num}
            </span>
            <div className={s.tag ? "pt-[0.4rem]" : undefined}>
              {s.tag ? (
                <p className="font-mono text-[0.6rem] uppercase tracking-[0.12em] text-accent">
                  {s.tag}
                </p>
              ) : null}
              <h3
                className={`${
                  s.tag ? "mt-[0.25rem]" : "flex min-h-[2rem] items-center"
                } font-display font-normal text-[clamp(1.2rem,2.4vw,1.5rem)] leading-[1.25] tracking-[-0.013em] text-ink`}
              >
                {s.title}
              </h3>
              <p className="mt-[0.35rem] max-w-[52ch] text-[0.9rem] leading-[1.55] text-ink-soft">
                {s.mech}
              </p>
            </div>
          </>
        );
        return fill ? (
          <m.li
            key={s.num}
            className={liClass}
            data-motion=""
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "0px 0px -12% 0px" }}
            transition={{ duration: 0.55, ease: EASE, delay: i * 0.28 }}
          >
            {content}
          </m.li>
        ) : (
          <li key={s.num} className={liClass}>
            {content}
          </li>
        );
      })}
    </ol>
  );
}
