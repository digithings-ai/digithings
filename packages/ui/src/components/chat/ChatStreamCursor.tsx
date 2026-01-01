/**
 * Streaming caret — the blinking block cursor that marks text still arriving
 * (canon §16): the ▍ read as a glyph-metric-free 7×14 accent block, steps(1)
 * blink, holding a steady block under reduced motion. Same mark as
 * digichat-ui's .dt-cur and digichat's .dc-term-streaming::after — both
 * rebuild on .chat-cursor. Accepts a ref so imperative typewriter effects
 * can toggle its visibility without re-rendering (see the stream-transcript
 * specimen). Keyframes + reduced-motion guard live in styles/chat-core.css.
 */
import type { Ref } from "react";

export type ChatStreamCursorProps = {
  className?: string;
  ref?: Ref<HTMLSpanElement>;
};

export function ChatStreamCursor({ className, ref }: ChatStreamCursorProps) {
  return (
    <span
      ref={ref}
      className={["chat-cursor", className ?? ""].filter(Boolean).join(" ")}
      aria-hidden="true"
    />
  );
}
