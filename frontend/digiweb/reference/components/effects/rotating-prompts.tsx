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

      <div className="prompt-shell" aria-live="polite">
        <span className="prompt-mark" aria-hidden="true">
          &gt;
        </span>
        <m.span
          key={reduced ? "static" : index}
          className="prompt-text"
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
