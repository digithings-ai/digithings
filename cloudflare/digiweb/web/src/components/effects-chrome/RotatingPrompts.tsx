"use client";

import { useEffect, useState } from "react";
import { m, useReducedMotion } from "motion/react";

/**
 * RotatingPrompts — the rotating hero teaser line promoted from the design
 * reference (effects/rotating-prompts): a mono `>` prompt shell whose text
 * cycles through real developer questions with a rise-in transition and a
 * blinking caret. The teaser is a door, not a poster — consumers pass the
 * prompts and typically link the shell into the live product. Link the
 * shell AS A SIBLING (wrap both in a common container and stretch the
 * anchor over it, e.g. an absolutely-positioned full-cover `<a>`), not by
 * nesting this component INSIDE an `<a>` — the shell renders a real
 * `<button>` (the pause control below), and nesting interactive content
 * inside other interactive content is invalid HTML: some browsers also
 * resolve the ambiguous click target inconsistently, and the button's own
 * preventDefault() cannot reliably cancel a `<button>`-inside-`<a>` parse
 * in every engine the way it can for a normal, non-nested ancestor click
 * listener.
 *
 * aria-live-safe: the shell announces politely; under reduced motion the
 * rotation stops and the FIRST prompt renders statically (also the no-JS /
 * server-rendered state, so the line always reads without JS). The caret's
 * @keyframes blink lives in styles/effects-chrome.css.
 *
 * WCAG 2.2.2 (Pause, Stop, Hide): the rotation runs longer than 5s and starts
 * automatically, so a visible pause control is required beyond the OS-level
 * reduced-motion escape hatch — a click on the shell (or Enter/Space, since
 * it is a real button) toggles it, aria-pressed carries the state.
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
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (reduced || paused || prompts.length < 2) return;
    const timer = setInterval(() => setIndex((i) => (i + 1) % prompts.length), intervalMs);
    return () => clearInterval(timer);
  }, [reduced, paused, prompts.length, intervalMs]);

  if (prompts.length === 0) return null;
  const current = prompts[reduced ? 0 : index % prompts.length];
  const showPauseControl = !reduced && prompts.length > 1;

  return (
    <div
      className={`flex items-baseline gap-[0.55rem] rounded-none border border-hair bg-surface px-[1.2rem] py-[1rem] font-mono text-[0.9rem] min-h-[3.4rem]${
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
      {showPauseControl ? (
        <button
          type="button"
          className="prompt-pause ml-auto"
          // Belt-and-suspenders even though the header comment now tells
          // consumers to link the shell as a SIBLING, not by nesting it
          // inside an <a>: stopPropagation alone does NOT stop an ancestor
          // <a>'s native navigation — only preventDefault does (the
          // anchor's default action is checked once against the event's
          // defaultPrevented flag after the full bubble phase, regardless
          // of where propagation was stopped) — so both are kept: preventDefault
          // so a click meant to pause never also navigates away, stopPropagation
          // so it never also fires some other ancestor's own click handler.
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setPaused((p) => !p);
          }}
          aria-pressed={paused}
          aria-label={paused ? "Resume rotating prompts" : "Pause rotating prompts"}
        >
          {paused ? (
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true">
              <path d="M6 4l14 8-14 8z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor" aria-hidden="true">
              <rect x="5" y="4" width="5" height="16" />
              <rect x="14" y="4" width="5" height="16" />
            </svg>
          )}
        </button>
      ) : null}
    </div>
  );
}
