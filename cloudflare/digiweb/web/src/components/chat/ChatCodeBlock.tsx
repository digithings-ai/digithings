"use client";
/**
 * Fenced code + copy affordance for <ChatMarkdown> (#1418): a hairline
 * figure with a microtype caption (language label · copy) over verbatim
 * code. The copy button is the only stateful piece — it flips to `copied`
 * for a beat via navigator.clipboard and silently no-ops where the API is
 * unavailable (e.g. cross-origin iframes — the digichat embed rule).
 * <ChatCopyButton> is exported solo so transcripts can pin the same
 * affordance to whole turns (digichat-ui's .dc-msg-copy / .dc-code-copy
 * rebuild on it). Box surface, caption row, and button mechanics live in
 * styles/chat-core.css.
 */
import { useState } from "react";

export type ChatCopyButtonProps = {
  /** Payload written to the clipboard. */
  text: string;
  ariaLabel?: string;
  className?: string;
};

export function ChatCopyButton({ text, ariaLabel = "Copy", className }: ChatCopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const cls = ["chat-md-copy", copied ? "is-copied" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <button
      type="button"
      className={cls}
      aria-label={ariaLabel}
      onClick={() =>
        navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          },
          () => {},
        )
      }
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

export type ChatCodeBlockProps = {
  /** Raw source — rendered verbatim and used as the copy payload. */
  code: string;
  /** Caption language label, e.g. `python`. */
  lang?: string;
  className?: string;
};

export function ChatCodeBlock({ code, lang, className }: ChatCodeBlockProps) {
  return (
    <figure className={["chat-md-code", className ?? ""].filter(Boolean).join(" ")}>
      <figcaption>
        <span>{lang}</span>
        <ChatCopyButton text={code} ariaLabel="Copy code" />
      </figcaption>
      <pre>
        <code>{code}</code>
      </pre>
    </figure>
  );
}
