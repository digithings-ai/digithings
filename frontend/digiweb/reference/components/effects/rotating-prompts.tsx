"use client";

import { useEffect, useState } from "react";
import { m, useReducedMotion } from "motion/react";

/** x.ai's rotating hero teasers + cursor's codebase Q&A, translated: the
 *  prompts are REAL quant questions, and in production each one links into
 *  digichat pre-filled — the teaser is a door, not a poster. */
const PROMPTS = [
  "size a kelly-capped BTC position at 2x leverage",
  "explain this drawdown against the regime flags",
  "backtest trend_xsec on ETH, last eight years",
  "which indicators disagree with the entry signal?",
];

export function RotatingPrompts() {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduced) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % PROMPTS.length), 3200);
    return () => clearInterval(timer);
  }, [reduced]);

  return (
    <section className="section-block accent-digichat" id="rotating-prompts">
      <p className="kicker">{"// rotating prompts"}</p>
      <h2 className="title">The teaser is a door.</h2>
      <p className="section-copy">
        Rotating hero prompts, but every prompt is a real developer question — never marketing
        copy — and each one opens the live chat pre-filled. Under reduced motion the rotation
        stops on the first prompt.
      </p>

      {/* Token-backed Tailwind utilities via the @theme bridge: the static shell
          (layout + border/surface + mono type) and the mark/text colours migrate
          cleanly. Off-scale rem values stay arbitrary to preserve the exact look.
          The blinking caret keeps its @keyframes rule in effects.css. */}
      <div
        className="mt-[1.2rem] flex items-baseline gap-[0.55rem] rounded-[12px] border border-hair bg-surface px-[1.2rem] py-[1rem] font-mono text-[0.9rem] min-h-[3.4rem]"
        aria-live="polite"
      >
        <span className="text-accent" aria-hidden="true">
          &gt;
        </span>
        <m.span
          key={reduced ? "static" : index}
          className="text-ink"
          initial={reduced ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
        >
          {PROMPTS[reduced ? 0 : index]}
        </m.span>
        <span className="prompt-caret" aria-hidden="true" />
      </div>
    </section>
  );
}
