"use client";

import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import type { MotionValue } from "motion/react";
import { useRef } from "react";

const TEXT =
  "Every number here traces to a real backtest nothing is invented and nothing is rounded";
const WORDS = TEXT.split(" ");

/**
 * Timing over the pinned track: every word reaches full visibility by
 * REVEAL_END (70% of track progress). The remaining 30% holds the finished
 * line on screen while it is still pinned, so the text can never leave the
 * viewport before it is fully legible.
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
  // cannot express this pinned-track mapping (it rises then falls). Arbitrary
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

export function WordRevealReference() {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  });

  return (
    <section className="section-block word-reveal" id="word-reveal">
      <p className="kicker">{"// word reveal — pinned blur"}</p>
      <h2 className="title">The claim holds until it is legible.</h2>
      <p className="section-copy">
        The full-drama variant, reserved for the one hero claim per page. The line pins to the
        viewport while scroll drives each word in from blur; the reveal completes at 70% of the
        track and the finished line holds for the remaining 30% — it cannot scroll away
        half-read. Under reduced motion the final state renders statically.
      </p>
      <div className={`wr-track${reduced ? " is-static" : ""}`} ref={trackRef}>
        <div className="wr-sticky">
          <p className="word-line" aria-label={TEXT}>
            <span aria-hidden="true">
              {reduced
                ? TEXT
                : WORDS.map((word, idx) => (
                    <RevealWord
                      key={`${word}-${idx}`}
                      index={idx}
                      total={WORDS.length}
                      text={word}
                      progress={scrollYProgress}
                    />
                  ))}
            </span>
          </p>
        </div>
      </div>
    </section>
  );
}
