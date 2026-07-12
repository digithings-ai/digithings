"use client";

import { useEffect, useRef } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";

/**
 * StatCounter — the count-up metric strip promoted from the design reference
 * (data/stat-counter): figures count up from zero the first time the strip
 * scrolls into view, the one place a number earns a little motion. The running
 * value is written straight to the DOM node (no per-frame re-render); mono,
 * tabular numerals keep the digits from reflowing. Fires once; reduced motion
 * and no-JS both show the final figure immediately (SSR ships the final value).
 *
 * Hairline dividers between stats are sibling-index CSS (styles/metrics.css):
 * left hairlines on every stat but the first, re-derived for the 2-up collapse
 * below 720px. Client component — in-view observer + imperative count.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/metrics.css";
 *                 @source "<path-to>/digiweb/web/src/components/metrics";
 */
export type CounterStat = {
  /** Final numeric value the counter lands on. */
  value: number;
  /** Fixed decimal places; omitted → rounded + locale-grouped. */
  decimals?: number;
  /** Literal prefix — "$", "+" … */
  prefix?: string;
  /** Literal suffix — "%", "×", "k" … */
  suffix?: string;
  /** Mono micro-caps label under the figure. */
  label: string;
};

const COLS: Record<2 | 3 | 4, string> = {
  2: "grid-cols-2",
  3: "grid-cols-3",
  4: "grid-cols-4",
};

function format(v: number, s: CounterStat) {
  const n = s.decimals ? v.toFixed(s.decimals) : Math.round(v).toLocaleString();
  return `${s.prefix ?? ""}${n}${s.suffix ?? ""}`;
}

function CountUp({ stat }: { stat: CounterStat }) {
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
    <div ref={wrapRef} className="sc-stat px-[1.2rem] py-[1.4rem]">
      <span
        ref={valueRef}
        className="block font-mono text-[clamp(1.6rem,4vw,2.4rem)] tabular-nums tracking-[-0.01em] text-accent"
      >
        {format(stat.value, stat)}
      </span>
      <span className="mt-[0.35rem] block font-mono text-[0.62rem] uppercase tracking-[0.1em] text-ink-mute">
        {stat.label}
      </span>
    </div>
  );
}

export function StatCounter({
  stats,
  columns = 4,
  className,
}: {
  stats: CounterStat[];
  /** Desktop stats per row (collapses to 2 below 720px). */
  columns?: 2 | 3 | 4;
  className?: string;
}) {
  return (
    <div
      className={`stat-counter grid ${COLS[columns]} overflow-hidden rounded-[12px] border border-hair bg-surface max-[720px]:grid-cols-2${
        className ? ` ${className}` : ""
      }`}
    >
      {stats.map((stat) => (
        <CountUp key={stat.label} stat={stat} />
      ))}
    </div>
  );
}
