"use client";

import { useId, useState } from "react";

/**
 * Accordion — a single-open disclosure over the FAQ. Each header is a real
 * button (Enter/Space toggle, aria-expanded/aria-controls), and the open panel
 * animates its own height via a grid-template-rows transition — no measuring, no
 * layout jump — while the chevron turns. Reduced motion snaps it open. Static
 * interactive display template.
 */
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

      <div className="mt-[1.2rem] overflow-hidden rounded-[12px] border border-hair bg-surface/40">
        {ITEMS.map((it, i) => {
          const isOpen = open === i;
          return (
            <div
              className={`acc-item border-t border-hair first:border-t-0${isOpen ? " open" : ""}`}
              key={it.q}
            >
              <h3 className="m-0 font-normal [font-size:inherit]">
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
                <div className="overflow-hidden">
                  <p className="m-0 max-w-[62ch] px-[1.1rem] pb-[1.1rem] text-[0.86rem] leading-[1.6] text-ink-soft">
                    {it.a}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
