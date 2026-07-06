"use client";

import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import { useRef } from "react";

const WORDS =
  "Every number here traces to a real backtest nothing is invented and nothing is rounded".split(" ");

function RevealWord({
  index,
  total,
  text,
  progress,
}: {
  index: number;
  total: number;
  text: string;
  progress: ReturnType<typeof useScroll>["scrollYProgress"];
}) {
  const reduced = useReducedMotion();
  const start = index / total;
  const end = Math.min(1, start + 0.34);

  const opacity = useTransform(progress, [start, end], [0.08, 1]);
  const y = useTransform(progress, [start, end], [7, 0]);
  const blur = useTransform(progress, [start, end], [10, 0]);
  const filter = useTransform(blur, (v) => `blur(${v}px)`);

  if (reduced) {
    return <span className="word final">{text}</span>;
  }

  return (
    <m.span className="word" style={{ opacity, y, filter }}>
      {text}
    </m.span>
  );
}

export function WordRevealReference() {
  const wrapRef = useRef<HTMLElement | null>(null);
  const { scrollYProgress } = useScroll({
    target: wrapRef,
    offset: ["start end", "end start"],
  });

  return (
    <section className="section-block word-reveal" id="word-reveal" ref={wrapRef}>
      <div className="section-head">
        <p className="kicker">{"// word reveal typography"}</p>
        <h2 className="title">Continuous scroll-linked reveal with reduced-motion fallback.</h2>
      </div>
      <p className="word-line" aria-label={WORDS.join(" ")}>
        {WORDS.map((word, idx) => (
          <RevealWord
            key={`${word}-${idx}`}
            index={idx}
            total={WORDS.length}
            text={word}
            progress={scrollYProgress}
          />
        ))}
      </p>
    </section>
  );
}
