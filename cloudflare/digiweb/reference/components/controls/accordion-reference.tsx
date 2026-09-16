"use client";

import { useState } from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@digithings/web/ui";

/**
 * Accordion — a single-open disclosure over the FAQ, composed from the stock
 * Collapsible. One panel is open at a time (the open index is app state), the
 * panel animates from the primitive's measured height
 * (`--collapsible-panel-height`) — no layout jump — and the chevron turns off
 * the root's `data-open` attribute. The trigger is the kit part, so
 * Enter/Space toggling and aria-expanded/aria-controls wiring come from
 * Base UI.
 *
 * Wave 1: `.acc-*` is gone; the old grid-template-rows trick and its
 * `.on`-class toggling are replaced by the primitive's own state attributes
 * and utilities.
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

  return (
    <section className="section-block">
      <p className="kicker">{"// accordion"}</p>
      <h2 className="title">One question open at a time.</h2>
      <p className="section-copy">
        A single-open disclosure: the panel animates from its measured height — no layout jump — and
        the chevron turns off the root&apos;s <code>data-open</code> state. Each header is the kit
        trigger (Enter/Space toggle), wired with <code>aria-expanded</code> /{" "}
        <code>aria-controls</code> by the primitive.
      </p>

      <div className="mt-[1.2rem] overflow-hidden rounded-none border border-hair bg-surface/40">
        {ITEMS.map((it, i) => (
          <Collapsible
            key={it.q}
            open={open === i}
            onOpenChange={(isOpen) => setOpen(isOpen ? i : null)}
            className="group border-t border-hair first:border-t-0"
          >
            <CollapsibleTrigger className="flex w-full items-center justify-between gap-4 px-[1.1rem] py-[1rem] font-mono text-[0.86rem] text-ink transition-colors hover:text-accent group-data-open:text-accent">
              <span>{it.q}</span>
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rotate-45 border-r-[1.6px] border-b-[1.6px] border-current transition-transform duration-300 group-data-open:-rotate-135"
              />
            </CollapsibleTrigger>
            <CollapsibleContent className="overflow-hidden transition-[height] duration-300 ease-out data-open:h-[var(--collapsible-panel-height)] data-starting-style:h-0 data-ending-style:h-0 data-closed:h-0">
              <p className="m-0 max-w-[62ch] px-[1.1rem] pb-[1.1rem] text-[0.86rem] leading-[1.6] text-ink-soft">
                {it.a}
              </p>
            </CollapsibleContent>
          </Collapsible>
        ))}
      </div>
    </section>
  );
}
