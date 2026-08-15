/**
 * Chat transcript — the term-surface scrollback pane behind the chatbot
 * family (#1418): a rounded terminal wash (bg-term-bg / term-hair, mono)
 * framing a column of <ChatMessage> turns. `session` draws the faint
 * "digichat — session" header as ::before chrome; `flat` drops the floating
 * shadow (the stream-transcript read); `scroll`/`live` turn the pane into a
 * live thread (digichat-ui's .dc-thread rebuilds on this: overflow-y auto,
 * thin scrollbar, contained overscroll, polite live region — the consumer
 * owns scroll position). The pane deliberately sets no row gap, text size,
 * or max-width: density is the consumer's call via className (the reference
 * uses gap-[0.7rem] for turn stacks, leading-[2.1] for dense scrollback).
 * Shadow, light-theme surface override, and the session ::before live in
 * styles/chat-core.css (import it once app-wide).
 */
import type { ReactNode } from "react";

export type ChatTranscriptProps = {
  children?: ReactNode;
  /** Faint session header line, e.g. `digichat — session`; omit for none. */
  session?: string;
  /** Drop the pane's floating shadow (flush embeds, dense scrollback). */
  flat?: boolean;
  /** Scrollable live-thread behavior (overflow-y auto, thin scrollbar). */
  scroll?: boolean;
  /** Announce streamed-in turns politely (aria-live region). */
  live?: boolean;
  className?: string;
  "aria-label"?: string;
};

export function ChatTranscript({
  children,
  session,
  flat,
  scroll,
  live,
  className,
  "aria-label": ariaLabel,
}: ChatTranscriptProps) {
  const cls = [
    "chat-transcript",
    flat ? "chat-transcript--flat" : "",
    scroll ? "chat-transcript--scroll min-h-0 overflow-y-auto overscroll-contain" : "",
    "flex flex-col rounded-[12px] border border-term-hair bg-term-bg px-[1.15rem] pt-[1rem] pb-[1.2rem] font-mono",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div
      className={cls}
      data-session={session}
      aria-label={ariaLabel}
      aria-live={live ? "polite" : undefined}
      aria-atomic={live ? false : undefined}
    >
      {children}
    </div>
  );
}
