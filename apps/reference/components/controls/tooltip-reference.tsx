"use client";

import {
  Button,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@digithings/ui/ui";

/**
 * Tooltip — the stock Tooltip family from `@digithings/ui/ui`. A label that
 * surfaces on hover and keyboard focus, positioned per placement, arrowed by
 * the kit, and animated by the stock data-open/data-closed utility set. Escape
 * dismisses it; the primitive wires aria-describedby to the trigger.
 *
 * Wave 1: the hand-built `.tt-*` bubble is gone — `side` replaces the
 * `.tt--{placement}` classes, triggers are the kit Button, and the info glyph
 * keeps its accessible name on the trigger.
 */
export function TooltipReference() {
  return (
    <TooltipProvider>
      <section className="section-block">
        <p className="kicker">{"// tooltip"}</p>
        <h2 className="title">A hint, on demand.</h2>
        <p className="section-copy">
          A label that surfaces on hover <em>and</em> keyboard focus, positioned on its own side of
          the trigger with the kit&apos;s arrow. Escape dismisses it;{" "}
          <code>aria-describedby</code> ties it to the control so it&apos;s announced. Four
          placements, and a richer one on an info glyph.
        </p>

        <div className="mt-[1.2rem] flex flex-wrap items-center gap-[1.7rem]">
          <Tooltip>
            <TooltipTrigger render={<Button variant="outline" />}>
              top
            </TooltipTrigger>
            <TooltipContent side="top">Ships to paper first</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger render={<Button variant="outline" />}>
              right
            </TooltipTrigger>
            <TooltipContent side="right">Routes through the sizer</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger render={<Button variant="outline" />}>
              bottom
            </TooltipTrigger>
            <TooltipContent side="bottom">Gated behind a human</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger render={<Button variant="outline" />}>
              left
            </TooltipTrigger>
            <TooltipContent side="left">Replays the ledger</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger
              render={<Button variant="ghost" size="icon-sm" aria-label="What is profit factor?" />}
            >
              <svg
                viewBox="0 0 24 24"
                width="15"
                height="15"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="12" cy="12" r="9" />
                <path d="M12 11v5M12 8v.5" />
              </svg>
            </TooltipTrigger>
            <TooltipContent side="top">
              Profit factor — gross profit ÷ gross loss. Above 1 is net positive.
            </TooltipContent>
          </Tooltip>
        </div>
      </section>
    </TooltipProvider>
  );
}
