"use client";

import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import type { MotionValue } from "motion/react";
import { useRef } from "react";

const TEXT = "The outline is the promise the fill is the proof";
const WORDS = TEXT.split(" ");
/** The closing word fills with the accent, per the house .colo-word pattern. */
const ACCENT_INDEX = WORDS.length - 1;

/** Same hold contract as the other variants: done by 70%, held for the last 30%. */
const REVEAL_END = 0.7;
const WORD_SPAN = 0.18;

function wordWindow(index: number, total: number): [number, number] {
  const start = (index / Math.max(1, total - 1)) * (REVEAL_END - WORD_SPAN);
  return [start, start + WORD_SPAN];
}

function OutlineWord({
  index,
  total,
  text,
  accent,
  progress,
}: {
  index: number;
  total: number;
  text: string;
  accent: boolean;
  progress: MotionValue<number>;
}) {
  const [start, end] = wordWindow(index, total);
  const fill = useTransform(progress, [start, end], [0, 100]);
  const color = useTransform(
    fill,
    (v) =>
      `color-mix(in srgb, ${accent ? "var(--accent)" : "var(--ink)"} ${v.toFixed(1)}%, transparent)`,
  );

  return (
    <m.span className={`wr-outline-word${accent ? " is-accent" : ""}`} style={{ color }}>
      {text}
    </m.span>
  );
}

export function WordRevealOutline() {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start start", "end end"],
  });

  return (
    <section className="section-block wr-outline" id="word-reveal-outline">
      <p className="kicker">{"// word reveal — outline fill"}</p>
      <h2 className="title">Type as a graphic, then as a message.</h2>
      <p className="section-copy">
        For display moments only — colophons, section breaks, the last line of a page. A hairline
        stroke states the shape first; scroll pours solid ink into each word and the closing word
        takes the accent. Browsers without text-stroke get solid, readable text instead of
        invisible outlines.
      </p>
      <div className={`wr-track${reduced ? " is-static" : ""}`} ref={trackRef}>
        <div className="wr-sticky">
          <p
            className={`word-line wr-outline-line${reduced ? " is-final" : ""}`}
            aria-label={TEXT}
          >
            <span aria-hidden="true">
              {WORDS.map((word, idx) =>
                reduced ? (
                  <span
                    key={`${word}-${idx}`}
                    className={`wr-outline-word${idx === ACCENT_INDEX ? " is-accent" : ""}`}
                  >
                    {word}
                  </span>
                ) : (
                  <OutlineWord
                    key={`${word}-${idx}`}
                    index={idx}
                    total={WORDS.length}
                    text={word}
                    accent={idx === ACCENT_INDEX}
                    progress={scrollYProgress}
                  />
                ),
              )}
            </span>
          </p>
        </div>
      </div>
    </section>
  );
}
