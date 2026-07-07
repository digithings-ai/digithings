"use client";

import { useRef, useState } from "react";
import { useInView } from "motion/react";

const STEPS = [
  "The user wants an 8-year backtest of trend_xsec on ETH.",
  "trend_xsec is cross-sectional, but this is a single symbol — fall back to the time-series variant.",
  "Default fees look wrong for ETH-USD; use the venue's maker/taker schedule.",
  "Cap sizing with Kelly at 0.5× so the drawdown stays bounded.",
  "Route the run through digiquant · nautilus and stream the tearsheet back.",
];

export function ChatThinkingReference() {
  const [open, setOpen] = useState(true);
  const scopeRef = useRef<HTMLDivElement | null>(null);
  const inView = useInView(scopeRef, { amount: 0.4, once: true });

  return (
    <section className="section-block" ref={scopeRef}>
      <p className="kicker">{"// thinking chain"}</p>
      <h2 className="title">Reasoning, folded by default.</h2>
      <p className="section-copy">
        Before the answer, the model&apos;s chain of thought collapses into a single chip — expand
        it to audit the steps, leave it folded to just read the result. The steps stream in as they
        arrive; a live run pulses, a finished one reports how long it took. Reduced motion shows the
        whole chain at rest.
      </p>

      <div className="chat-surface">
        <div className="chat-turn chat-turn--user">
          <div className="chat-bubble chat-bubble--user">
            backtest trend_xsec on ETH, last eight years
          </div>
        </div>

        <div className="chat-turn chat-turn--assistant">
          <span className="chat-mark" aria-hidden="true">
            ▸
          </span>
          <div className="chat-stack">
            <button
              type="button"
              className={`think-chip${open ? " open" : ""}`}
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              <span className="think-caret" aria-hidden="true" />
              <span className="think-dot" aria-hidden="true" />
              Thought for 4.2s
              <span className="think-count">{STEPS.length} steps</span>
            </button>

            {open ? (
              <ol className={`think-steps${inView ? " in" : ""}`}>
                {STEPS.map((s, i) => (
                  <li key={s} style={{ transitionDelay: `${i * 90}ms` }}>
                    {s}
                  </li>
                ))}
              </ol>
            ) : null}

            <div className="chat-bubble">
              Done — trend_xsec (time-series), 8y ETH-USD, Kelly-capped 0.5×. PF 2.31, max drawdown
              −18.4%. Tearsheet below.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
