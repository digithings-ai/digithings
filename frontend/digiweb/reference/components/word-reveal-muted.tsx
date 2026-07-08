"use client";

import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import type { MotionValue } from "motion/react";
import { useRef } from "react";

const TEXT =
  "The whole sentence is readable before anything moves scroll only decides which word carries the weight";
const WORDS = TEXT.split(" ");

/** Same hold contract as the blur variant: done by 70%, held for the last 30%. */
const REVEAL_END = 0.7;
const WORD_SPAN = 0.18;

function wordWindow(index: number, total: number): [number, number] {
  const start = (index / Math.max(1, total - 1)) * (REVEAL_END - WORD_SPAN);
  return [start, start + WORD_SPAN];
}

function MutedWord({
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
    <m.span className="wr-muted-word" style={{ color }}>
      {text}
    </m.span>
  );
}

export function WordRevealMuted() {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  });

  return (
    <section className="section-block wr-muted" id="word-reveal-muted">
      <p className="kicker">{"// word reveal — muted base"}</p>
      <h2 className="title">Emphasis, never a gate.</h2>
      <p className="section-copy">
        Every word sits at the muted ink from the first frame, so the copy survives a skim with
        zero scrolling. Progress only deepens each word to full ink — pure color interpolation,
        no opacity or blur — steering the eye without ever gating the message. Use it for
        supporting claims mid-page where legibility must be unconditional.
      </p>
      <div className={`wr-track${reduced ? " is-static" : ""}`} ref={trackRef}>
        <div className="wr-sticky">
          <p className="word-line" aria-label={TEXT}>
            <span aria-hidden="true">
              {reduced
                ? TEXT
                : WORDS.map((word, idx) => (
                    <MutedWord
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
