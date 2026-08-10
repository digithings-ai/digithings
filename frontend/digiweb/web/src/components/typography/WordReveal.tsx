"use client";

import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import type { MotionValue } from "motion/react";
import { useRef } from "react";

/**
 * WordReveal — the full-drama pinned-blur reveal promoted from the design
 * reference (typography/word-reveal). Reserved for the one hero claim per page:
 * words fill from blur as the line rides up the viewport — the reveal starts
 * as soon as the line enters and completes by the time it reaches
 * mid-viewport, where a short sticky hold gives the finished claim one beat
 * before the page flows on. It can never scroll away half-read. Under
 * `prefers-reduced-motion` — or with no JS at all (`html.no-js`) — the final
 * text renders statically, fully legible, with no empty scroll gap.
 *
 * The pinned-track / display-line / `.word` mechanics live in
 * styles/word-reveal.css (kept CSS per the migrate-vs-leave rule: the 150vh
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
 * Timing against ["start end", "start start"] scroll progress (0 = the track's
 * top enters the viewport bottom, 1 = it reaches the viewport top, which is
 * the instant the sticky pin engages with the line at mid-viewport):
 * the line's own top clears the viewport bottom around ~0.4, so words start
 * filling the moment the line is visible (REVEAL_START) and every word is
 * fully legible by REVEAL_END ≈ the mid-viewport pin. The pinned remainder of
 * the track (track height − 100vh) is a short hold, not reveal time.
 */
const REVEAL_START = 0.4;
const REVEAL_END = 0.98;
const WORD_SPAN = 0.18;

function wordWindow(index: number, total: number): [number, number] {
  const start =
    REVEAL_START +
    (index / Math.max(1, total - 1)) * (REVEAL_END - WORD_SPAN - REVEAL_START);
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
  // 0 = track top enters the viewport bottom; 1 = track top reaches the
  // viewport top (the sticky pin engages, line at mid-viewport). The reveal
  // maps onto the line's entry ride — see the timing note above.
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start end", "start start"],
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
