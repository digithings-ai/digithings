"use client";

import { useId, useState } from "react";

const ITEMS = [
  {
    q: "Is my data ever sent anywhere?",
    a: "No. digithings is self-hosted and BYOK — your keys, your infra. Audit logging is on by default so you can prove it.",
  },
  {
    q: "Can I trust a backtest?",
    a: "Only if you can re-run it. Every tearsheet is deterministic on a NautilusTrader core, with a full trade ledger behind the numbers.",
  },
  {
    q: "How do live trades get approved?",
    a: "Promotion runs backtest → paper → loopback → live, and every rung is a human gate. Nothing reaches a broker on its own.",
  },
  {
    q: "Which models can I use?",
    a: "Any — LiteLLM routes to the provider you bring a key for, with caching. Swap models without touching the strategy code.",
  },
];

export function AccordionReference() {
  const [open, setOpen] = useState<number | null>(0);
  const base = useId();

  return (
    <section className="section-block">
      <p className="kicker">{"// accordion"}</p>
      <h2 className="title">One question open at a time.</h2>
      <p className="section-copy">
        A single-open disclosure: the panel animates its own height with a{" "}
        <code>grid-template-rows</code> transition — no measuring, no layout jump — and the chevron
        turns. Each header is a real button (Enter/Space toggle), wired with{" "}
        <code>aria-expanded</code> / <code>aria-controls</code>. Reduced motion snaps it open.
      </p>

      <div className="acc">
        {ITEMS.map((it, i) => {
          const isOpen = open === i;
          return (
            <div className={`acc-item${isOpen ? " open" : ""}`} key={it.q}>
              <h3 className="acc-h">
                <button
                  type="button"
                  className="acc-head"
                  aria-expanded={isOpen}
                  aria-controls={`${base}-p-${i}`}
                  id={`${base}-h-${i}`}
                  onClick={() => setOpen(isOpen ? null : i)}
                >
                  <span>{it.q}</span>
                  <span className="acc-chev" aria-hidden="true" />
                </button>
              </h3>
              <div
                className="acc-panel"
                role="region"
                id={`${base}-p-${i}`}
                aria-labelledby={`${base}-h-${i}`}
              >
                <div className="acc-panel-inner">
                  <p className="acc-body">{it.a}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
