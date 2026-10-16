"use client";

import { ChatMessage } from "../chat/ChatMessage";
import { TerminalStepCaret } from "./TerminalStepCaret";

/**
 * Chat response loader — the wait between sending a message and the first
 * token of the answer. It occupies the assistant turn it is about to become:
 * a <ChatMessage role="assistant"> row, so the `▸` marker, the
 * `1.25rem minmax(0,1fr)` grid and the body ink are the transcript's own
 * (canon §16) and nothing shifts when the real turn replaces it. The body is
 * the house type-out — the running step types out at the block cursor, holds,
 * deletes, and the next one follows — so the same caret that will stream the
 * answer is already blinking while it is being written.
 *
 * The step labels are a promise about what is happening, so drive them from
 * what IS happening wherever the transport can say: pass `activeIndex` from
 * the stream's stage events or tool-call names and the caret erases and
 * retypes on each change. Uncontrolled, it cycles the default path — which is
 * honest for the first second and vague after that, so prefer real steps.
 *
 * Snappier than the boot loader by design (900ms dwell, cycling): this one is
 * usually replaced within a second or two, and a slow hold there reads as a
 * stall rather than as work.
 *
 * One motion moment: the caret. `prefers-reduced-motion` shows the active
 * step's label whole with the caret still — which uncontrolled is the first,
 * since the internal clock never starts; see <TerminalStepCaret>.
 */
export type ChatResponseLoaderProps = {
  /** Stages, in order. Defaults to the common path. */
  steps?: string[];
  /** Caller-driven stage; omit to cycle on the internal clock. */
  activeIndex?: number;
  className?: string;
};

/** The common path. Illustrative — feed the real stages where you have them. */
const RESPONSE_STEPS = [
  "thinking",
  "routing through digigraph",
  "gathering context",
  "composing the answer",
];

/**
 * Snappier than the boot loader's 1200ms. Exported because a surface that
 * already owns its assistant row (digichat's `.dc-msg`, which predates canon
 * §16) renders <TerminalStepCaret> directly rather than nesting this component
 * inside its own row and doubling the marker — it still has to wait at the
 * same cadence, and a second literal is how the two drift apart.
 */
const RESPONSE_HOLD_MS = 900;

export function ChatResponseLoader({
  steps = RESPONSE_STEPS,
  activeIndex,
  className,
}: ChatResponseLoaderProps) {
  return (
    <ChatMessage role="assistant" tone="mute" className={className}>
      <TerminalStepCaret steps={steps} activeIndex={activeIndex} holdMs={RESPONSE_HOLD_MS} />
    </ChatMessage>
  );
}

export { RESPONSE_STEPS as CHAT_RESPONSE_STEPS, RESPONSE_HOLD_MS as CHAT_RESPONSE_HOLD_MS };
