"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";
import { ChatStreamCursor } from "@digithings/web";

/**
 * Step caret — the house type-out, applied to waiting. The label of the step
 * currently running types out at the blinking block cursor, holds long enough
 * to read, deletes, and the next step follows: the same grammar the animated
 * brand lockup uses to cycle module names (`AnimatedLockup`, symbols family),
 * which is why a loader built on it reads as the mark rather than as chrome.
 *
 * The caret is not redrawn — it is <ChatStreamCursor> (canon §16), so the
 * glyph-metric-free 7×14 accent block, the steps(1) blink and the
 * reduced-motion still all come from chat-core.css and never drift.
 *
 * Two things are load-bearing:
 *
 * - **Typing is priced per character, not per step.** A fixed slot makes a
 *   short label type at twice the speed of a long one and the rhythm limps —
 *   the lockup's rule, and the reason the cadence constants are per-char.
 *   Cadence diverges from the lockup's 140ms/char, which is tuned for 5-letter
 *   suffixes; a step label is a phrase, so it runs at 58ms. Keep labels under
 *   ~30 characters — the line does not wrap (the caret has to trail the text,
 *   and a wrapped caret lands in the margin), and 30 is what the boot surface
 *   holds on a 375px viewport.
 * - **The label is written straight to the DOM, not re-rendered.** A character
 *   is not a state change; `shownRef` tracks what is on screen so a step swap
 *   erases what was actually there. That also keeps the typed node out of the
 *   a11y tree — a live region on it would announce every keystroke — so the
 *   step is announced once, whole, from an `sr-only` `role="status"` sibling.
 *
 * Steps advance on the internal clock, or pass `activeIndex` to drive them
 * from real progress (a stream's tool-call names, a health-check phase) and
 * the caret erases and retypes on each change.
 *
 * `prefers-reduced-motion` renders the final state — the active step's label
 * whole, no typing, no deleting, the caret still — and the internal clock
 * never starts, so an uncontrolled caret holds its first step. A caller-driven
 * `activeIndex` still swaps the label: that is information, not decoration.
 * With scripts off the first step renders from `<noscript>`.
 */
export type TerminalStepCaretProps = {
  /** The steps, in order. The first is the reduced-motion / no-JS state. */
  steps: string[];
  /** Caller-driven step; omit to advance on the internal clock. */
  activeIndex?: number;
  /** When self-advancing: cycle (default), or stop on the last step. */
  loop?: boolean;
  /** Prompt mark before the label. Omit when the surface owns the marker. */
  mark?: ReactNode;
  /** Per-character type / erase cadence, and the beats between, in ms. */
  typeMs?: number;
  eraseMs?: number;
  holdMs?: number;
  restMs?: number;
  className?: string;
};

/** Per-character cadence. `erase/type` holds the lockup's 90/140 ratio. */
const TYPE_MS = 58;
const ERASE_MS = 37;
/** Dwell on a finished label, and the beat between erasing and typing. */
const HOLD_MS = 1200;
const REST_MS = 220;

export function TerminalStepCaret({
  steps,
  activeIndex,
  loop = true,
  mark,
  typeMs = TYPE_MS,
  eraseMs = ERASE_MS,
  holdMs = HOLD_MS,
  restMs = REST_MS,
  className,
}: TerminalStepCaretProps) {
  const reduced = useReducedMotion();
  const labelRef = useRef<HTMLSpanElement | null>(null);
  /** What is on screen right now — the DOM is written to, not re-rendered. */
  const shownRef = useRef("");
  const [ownIndex, setOwnIndex] = useState(0);

  const controlled = activeIndex !== undefined;
  const count = steps.length;
  const index = count === 0 ? 0 : (((controlled ? activeIndex : ownIndex) % count) + count) % count;
  const word = steps[index] ?? "";

  useEffect(() => {
    const node = labelRef.current;
    if (!node) return;

    const write = (text: string) => {
      shownRef.current = text;
      node.textContent = text;
    };

    if (reduced || !word) {
      write(word);
      return;
    }

    let timer = 0;
    const from = shownRef.current;
    let cut = from.length;
    let typed = 0;

    const type = () => {
      if (typed < word.length) {
        typed += 1;
        write(word.slice(0, typed));
        timer = window.setTimeout(type, typeMs);
        return;
      }
      // Settled. A controlled caret waits for the caller; an unlooped one
      // holds the last step for as long as the wait lasts.
      if (controlled) return;
      if (!loop && index >= count - 1) return;
      timer = window.setTimeout(() => setOwnIndex((i) => (i + 1) % count), holdMs);
    };

    const erase = () => {
      if (cut > 0) {
        cut -= 1;
        write(from.slice(0, cut));
        timer = window.setTimeout(erase, eraseMs);
        return;
      }
      timer = window.setTimeout(type, restMs);
    };

    erase();
    return () => window.clearTimeout(timer);
  }, [word, index, count, controlled, loop, reduced, typeMs, eraseMs, holdMs, restMs]);

  return (
    <span className={["tl-line", className ?? ""].filter(Boolean).join(" ")}>
      {mark ? (
        <span className="tl-mark" aria-hidden="true">
          {mark}
        </span>
      ) : null}
      {/* Typed imperatively — empty on the server so the first paint is the
          start of the type-out, not a frame of finished text that clears. */}
      <span className="tl-label" ref={labelRef} aria-hidden="true" />
      <noscript>
        <span className="tl-label">{steps[0] ?? ""}</span>
      </noscript>
      <ChatStreamCursor />
      <span className="sr-only" role="status">
        {word}
      </span>
    </span>
  );
}
