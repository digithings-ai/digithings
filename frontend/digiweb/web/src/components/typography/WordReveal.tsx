"use client";

import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import type { MotionValue } from "motion/react";
import { useRef } from "react";

/**
 * WordReveal — the full-drama pinned-blur reveal promoted from the design
 * reference (typography/word-reveal). Reserved for the one hero claim per page:
 * the line pins to the viewport while scroll drives each word in from blur; the
 * reveal completes at 70% of the pinned track and the finished line holds for
 * the remaining 30% so it can never scroll away half-read. Under
 * `prefers-reduced-motion` — or with no JS at all (`html.no-js`) — the final
 * text renders statically, fully legible, with no empty scroll gap.
 *
 * The pinned-track / display-line / `.word` mechanics live in
 * styles/word-reveal.css (kept CSS per the migrate-vs-leave rule: the 240vh
 * track, the sticky pin, and the reduced-motion + no-JS fallbacks). This
 * component carries the scroll→opacity/blur mapping and the token-backed
 * kicker/title utilities.
 *
 * Client component — scroll progress + per-word transforms. Motion via `m`
 * under a MotionProvider (LazyMotion). Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/word-reveal.css";
 *                 @source "<path-to>/digiweb/web/src/components/typography";
 */

/**
 * Timing over the pinned track: every word reaches full visibility by
 * REVEAL_END (70% of track progress); the remaining 30% holds the finished
 * line on screen while it is still pinned.
 */
const REVEAL_END = 0.7;
const WORD_SPAN = 0.18;

function wordWindow(index: number, total: number): [number, number] {
  const start = (index / Math.max(1, total - 1)) * (REVEAL_END - WORD_SPAN);
  return [start, start + WORD_SPAN];
}

function RevealWord({
  index,
  total,
  text,
  progress,
}: {
  index: number;
  total: number;
  text: string;
  progress: MotionValue<number>;
}) {
  const [start, end] = wordWindow(index, total);
  // Function transforms only: a numeric range-map on opacity gets compiled by
  // Motion into a native view()-timeline animation, whose enter/exit progress
  // cannot express this pinned-track mapping (it rises then holds). Arbitrary
  // functions are uncompilable, which pins every value to the JS scroll path.
  const wordProgress = (p: number) => Math.min(1, Math.max(0, (p - start) / (end - start)));
  const opacity = useTransform(progress, (p) => 0.08 + wordProgress(p) * 0.92);
  const y = useTransform(progress, (p) => (1 - wordProgress(p)) * 7);
  const filter = useTransform(progress, (p) => `blur(${(1 - wordProgress(p)) * 10}px)`);

  return (
    <m.span className="word" style={{ opacity, y, filter }}>
      {text}
    </m.span>
  );
}

export type WordRevealProps = {
  /** The claim to reveal — split on whitespace; each word animates in turn. */
  text: string;
  /** Optional mono kicker above the line. */
  kicker?: string;
  /** Optional serif title above the line. */
  title?: string;
  /** Anchor id on the block wrapper. */
  id?: string;
  /** Extra classes on the block wrapper. */
  className?: string;
};

export function WordReveal({ text, kicker, title, id, className }: WordRevealProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  });
  const words = text.split(" ");

  return (
    <div id={id} className={className}>
      {kicker ? (
        <p className="font-mono text-[0.8rem] tracking-[0.02em] text-accent">{kicker}</p>
      ) : null}
      {title ? (
        <h2 className="mt-[0.4rem] font-display text-[clamp(1.5rem,3vw,2.3rem)] font-normal leading-[1.12] tracking-[-0.01em] text-ink">
          {title}
        </h2>
      ) : null}
      <div className={`wr-track${reduced ? " is-static" : ""}`} ref={trackRef}>
        <div className="wr-sticky">
          <p className="word-line" aria-label={text}>
            <span aria-hidden="true">
              {reduced
                ? text
                : words.map((word, idx) => (
                    <RevealWord
                      key={`${word}-${idx}`}
                      index={idx}
                      total={words.length}
                      text={word}
                      progress={scrollYProgress}
                    />
                  ))}
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
