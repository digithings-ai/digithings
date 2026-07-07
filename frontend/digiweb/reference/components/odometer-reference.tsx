"use client";

import { useRef } from "react";
import { useInView, useReducedMotion } from "motion/react";

/**
 * Odometer counter — the mechanical digit-roll (Revolut's sleek counters), the
 * companion to the count-up stat. Each digit is a 0–9 reel; on scroll-into-view
 * every reel rolls to its target with a staggered delay. Non-digit characters
 * ($ , . %) sit static between reels. The whole figure carries an aria-label so
 * screen readers read the value once; reels are decorative. Reduced motion
 * drops the roll and shows the final value.
 */
const STATS = [
  { label: "equity under test", value: "$1,284,000" },
  { label: "backtests run", value: "3,102" },
  { label: "profit factor", value: "2.31" },
  { label: "modules", value: "12" },
];

function Odometer({ value }: { value: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { amount: 0.6, once: true });
  const reduced = useReducedMotion();
  const settled = inView || reduced;

  return (
    <span className="odo" ref={ref} aria-label={value}>
      {value.split("").map((c, i) =>
        /[0-9]/.test(c) ? (
          <span className="odo-reel" key={i} aria-hidden="true">
            <span
              className="odo-strip"
              style={{
                transform: `translateY(${-(settled ? Number(c) : 0) * 10}%)`,
                transitionDelay: `${i * 55}ms`,
              }}
            >
              {Array.from({ length: 10 }, (_, n) => (
                <span className="odo-digit" key={n}>
                  {n}
                </span>
              ))}
            </span>
          </span>
        ) : (
          <span className="odo-sep" key={i} aria-hidden="true">
            {c}
          </span>
        ),
      )}
    </span>
  );
}

export function OdometerReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// odometer"}</p>
      <h2 className="title">Numbers that roll into place.</h2>
      <p className="section-copy">
        The mechanical counterpart to the count-up: each digit is a reel that rolls to its value
        when the figure scrolls into view, staggered left to right. Separators (<code>$ , .</code>)
        stay put; the value is announced once via <code>aria-label</code>. Reduced motion sets it
        without the roll.
      </p>

      <div className="odo-grid">
        {STATS.map((s) => (
          <div className="odo-cell" key={s.label}>
            <Odometer value={s.value} />
            <span className="odo-label">{s.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
