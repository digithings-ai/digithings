/**
 * Chat message — one turn of the digichat grammar (canon §16): a marker
 * column and a body on a `1.25rem minmax(0,1fr)` grid — the digichat
 * .dc-term-row geometry, and the convergence target for digichat-ui's
 * .dc-msg (marker ⇢ .dc-who, body ⇢ .dc-body). `>` marks the user, `▸` the
 * assistant, `·` system asides; markers carry the accent and stay out of
 * the a11y tree. `tone` picks the body ink explicitly (user turns default
 * to full ink, the rest to soft; an emphasized answer passes tone="ink") so
 * consumers never fight utility order. `streaming` appends the blink caret.
 * The row is position:relative (chat-core.css) so hover affordances — a
 * per-turn <ChatCopyButton>, digichat-ui's .dc-msg-copy — can pin to it.
 */
import type { ReactNode } from "react";
import { ChatStreamCursor } from "./ChatStreamCursor";

export type ChatRole = "user" | "assistant" | "system";

export type ChatTone = "ink" | "soft" | "mute";

const MARKERS: Record<ChatRole, string> = { user: ">", assistant: "▸", system: "·" };

const TONES: Record<ChatTone, string> = {
  ink: "text-ink",
  soft: "text-ink-soft",
  mute: "text-ink-mute",
};

export type ChatMessageProps = {
  role: ChatRole;
  /** Marker glyph override (digichat-ui marks assistant turns `·`). */
  marker?: ReactNode;
  /** Body ink; defaults to `ink` for user turns, `soft` otherwise. */
  tone?: ChatTone;
  /** Append the blinking stream caret after the body. */
  streaming?: boolean;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
};

export function ChatMessage({
  role,
  marker,
  tone,
  streaming,
  children,
  className,
  bodyClassName,
}: ChatMessageProps) {
  const bodyTone = TONES[tone ?? (role === "user" ? "ink" : "soft")];
  const cls = [
    `chat-msg chat-msg--${role}`,
    "grid grid-cols-[1.25rem_minmax(0,1fr)] items-baseline gap-[0.55rem]",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  const bodyCls = [
    "chat-msg-body min-w-0",
    bodyTone,
    role === "user" ? "whitespace-pre-wrap" : "",
    bodyClassName ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      <span className="chat-msg-marker text-accent" aria-hidden="true">
        {marker ?? MARKERS[role]}
      </span>
      <div className={bodyCls}>
        {children}
        {streaming ? <ChatStreamCursor /> : null}
      </div>
    </div>
  );
}
