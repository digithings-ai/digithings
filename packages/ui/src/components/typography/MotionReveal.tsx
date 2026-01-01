"use client";

import { m, useScroll, useTransform } from "motion/react";
import type { MotionValue } from "motion/react";
import { useRef } from "react";
import { useMotionSafe } from "../../motion/primitives";

/**
 * MotionReveal — the mid-page motion text, sibling to <WordReveal/>.
 *
 * <WordReveal/> is the full-drama hero claim: a 150vh pinned track whose words
 * fill from blur on the ride up, deliberately reserved for one claim per page
 * (its own docblock says so, and a second one on a page stacks 150vh of dead
 * scroll behind the footer). That grammar is wrong for a supporting claim —
 * the testimonial wall, a quoted voice — where the copy must read the moment
 * it is on screen and the page must keep moving.
 *
 * So this is the same idea at band scale, and NOT pinned: the words deepen in
 * order from muted to full ink as the line rides up the viewport, and they are
 * legible from the first frame — pure colour interpolation, no opacity or blur,
 * so the reveal steers the eye and never gates the message. The finished state
 * is reached by the time the line is mid-viewport; the track adds no height.
 * This is the treatment the reference gallery documents for "supporting claims
 * mid-page where legibility must be unconditional".
 *
 * Motion is scroll-linked per word; under `prefers-reduced-motion` — or with no
 * JS at all — the text renders in full ink immediately. `.word` comes from
 * styles/word-reveal.css and already carries both fallbacks:
 *
 *   @media (prefers-reduced-motion: reduce) { .word { opacity/transform/filter: … } }
 *   html.no-js .word { … }
 *
 * Wiring (in the consuming app): the word-reveal sheet must be imported, which
 * <WordReveal/> already requires —
 *   globals.css  @import "@digithings/ui/styles/word-reveal.css";
 */
const REVEAL_END = 0.86;
const WORD_SPAN = 0.2;

function wordWindow(index: number, total: number): [number, number] {
  const start = (index / Math.max(1, total - 1)) * Math.max(0, REVEAL_END - WORD_SPAN);
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
  const mix = useTransform(progress, [start, end], [0, 100]);
  const color = useTransform(
    mix,
    (v) => `color-mix(in srgb, var(--ink) ${v.toFixed(1)}%, var(--ink-mute))`,
  );

  return (
    <m.span className="word" style={{ color }}>
      {text}
    </m.span>
  );
}

export type MotionRevealProps = {
  /** The copy to spell out — split on whitespace; each word deepens in turn. */
  text: string;
  /** Extra classes on the inline wrapper. */
  className?: string;
};

export function MotionReveal({ text, className }: MotionRevealProps) {
  const trackRef = useRef<HTMLSpanElement | null>(null);
  // useMotionSafe(), not a raw reduced-motion read: SSR cannot know the media
  // query, so the server pass must always take the animated branch and the
  // real preference resolves one effect-tick later — the same hydration-safe
  // pattern <WordReveal/> uses (#2244).
  const safe = useMotionSafe();
  // The line's own ride: 0 when its top crosses 92% of the viewport, 1 by the
  // time its bottom reaches 55% — i.e. fully spelled out around mid-viewport,
  // and the element is never pinned, so the band keeps its natural height.
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start 0.92", "end 0.55"],
  });
  const words = text.split(" ");

  return (
    <m.span ref={trackRef} className={className}>
      {safe
        ? words.map((word, idx) => (
            <RevealWord
              key={`${word}-${idx}`}
              index={idx}
              total={words.length}
              text={word}
              progress={scrollYProgress}
            />
          ))
        : text}
    </m.span>
  );
}
