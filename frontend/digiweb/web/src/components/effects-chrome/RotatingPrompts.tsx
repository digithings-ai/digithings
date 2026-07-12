"use client";

import { useEffect, useState } from "react";
import { m, useReducedMotion } from "motion/react";

/**
 * RotatingPrompts — the rotating hero teaser line promoted from the design
 * reference (effects/rotating-prompts): a mono `>` prompt shell whose text
 * cycles through real developer questions with a rise-in transition and a
 * blinking caret. The teaser is a door, not a poster — consumers pass the
 * prompts and typically wrap the shell in a link into the live product.
 *
 * aria-live-safe: the shell announces politely; under reduced motion the
 * rotation stops and the FIRST prompt renders statically (also the no-JS /
 * server-rendered state, so the line always reads without JS). The caret's
 * @keyframes blink lives in styles/effects-chrome.css.
 *
 * Client component (interval state). Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/effects-chrome.css";
 *                 @source "<path-to>/digiweb/web/src/components/effects-chrome";
 */
export type RotatingPromptsProps = {
  /** The rotation, in order. First item is the reduced-motion / no-JS state. */
  prompts: string[];
  /** Dwell per prompt, ms. */
  intervalMs?: number;
  className?: string;
};

export function RotatingPrompts({ prompts, intervalMs = 3200, className }: RotatingPromptsProps) {
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (reduced || prompts.length < 2) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % prompts.length), intervalMs);
    return () => clearInterval(timer);
  }, [reduced, prompts.length, intervalMs]);

  if (prompts.length === 0) return null;
  const current = prompts[reduced ? 0 : index % prompts.length];

  return (
    <div
      className={`flex items-baseline gap-[0.55rem] rounded-[12px] border border-hair bg-surface px-[1.2rem] py-[1rem] font-mono text-[0.9rem] min-h-[3.4rem]${
        className ? ` ${className}` : ""
      }`}
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
        {current}
      </m.span>
      <span className="prompt-caret" aria-hidden="true" />
    </div>
  );
}
