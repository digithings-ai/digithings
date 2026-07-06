"use client";

import { useEffect, useRef } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";

type Stat = {
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  label: string;
};

const STATS: Stat[] = [
  { value: 8.72, decimals: 2, label: "profit factor" },
  { value: 75.9, decimals: 1, suffix: "%", label: "win rate" },
  { value: 3102, label: "backtests run" },
  { value: 12, label: "modules" },
];

function format(v: number, s: Stat) {
  const n = s.decimals ? v.toFixed(s.decimals) : Math.round(v).toLocaleString();
  return `${s.prefix ?? ""}${n}${s.suffix ?? ""}`;
}

function CountUp({ stat }: { stat: Stat }) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const valueRef = useRef<HTMLSpanElement | null>(null);
  const inView = useInView(wrapRef, { once: true, margin: "-15% 0px" });
  const reduced = useReducedMotion();

  // Write the running number straight to the DOM node — no per-frame React
  // re-render. SSR ships the final value (correct with no JS); the count only
  // runs once the strip scrolls into view.
  useEffect(() => {
    const node = valueRef.current;
    if (!node || !inView || reduced) return;
    const controls = animate(0, stat.value, {
      duration: 1.1,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        node.textContent = format(v, stat);
      },
    });
    return () => controls.stop();
  }, [inView, reduced, stat]);

  return (
    <div ref={wrapRef} className="sc-stat">
      <span ref={valueRef} className="sc-value">
        {format(stat.value, stat)}
      </span>
      <span className="sc-label">{stat.label}</span>
    </div>
  );
}

export function StatCounterReference() {
  return (
    <section className="section-block stat-counter">
      <p className="kicker">{"// stat counter"}</p>
      <h2 className="title">Numbers that arrive.</h2>
      <p className="section-copy">
        A metric strip that counts up from zero once it scrolls into view — the one place a number
        earns a little motion. Mono numerals, hairline dividers, tabular so the digits never
        reflow. Fires once; reduced motion and no-JS both show the final figure immediately.
      </p>

      <div className="sc-row">
        {STATS.map((stat) => (
          <CountUp key={stat.label} stat={stat} />
        ))}
      </div>
    </section>
  );
}
