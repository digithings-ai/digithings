"use client";

import { useRef, useState } from "react";

/**
 * Chat composer — the terminal prompt input: an auto-growing textarea with a live
 * character counter against a limit and a send affordance; echoes the last sent
 * line back into the scrollback. Interactive display template.
 */
const MAX = 2000;

export function ChatComposerReference() {
  const [value, setValue] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const areaRef = useRef<HTMLTextAreaElement | null>(null);

  const grow = () => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  };

  const send = () => {
    const text = value.trim();
    if (!text) return;
    setSent(text);
    setValue("");
    requestAnimationFrame(grow);
  };

  return (
    <section className="section-block">
      <p className="kicker">{"// composer"}</p>
      <h2 className="title">The textbox does the work.</h2>
      <p className="section-copy">
        The composer grows with the message up to a ceiling, then scrolls. Enter sends,
        Shift+Enter drops a line; a slash opens commands. Attachments, the active model, and a live
        character count sit on the tray beneath — send lights only when there&apos;s something to
        send.
      </p>

      <div className="chat-surface">
        {sent ? (
          <div className="chat-turn chat-turn--user">
            <div className="chat-bubble chat-bubble--user">{sent}</div>
          </div>
        ) : null}

        <div className="composer">
          <textarea
            ref={areaRef}
            className="composer-input"
            rows={1}
            placeholder="Ask digichat to backtest, search, or explain…"
            value={value}
            maxLength={MAX}
            onChange={(e) => {
              setValue(e.target.value);
              grow();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />

          <div className="composer-tray">
            <div className="composer-tools">
              <button type="button" className="composer-icon" aria-label="Attach a file">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.5 12.5 21a5 5 0 0 1-7-7l8-8a3.3 3.3 0 0 1 4.7 4.7l-8 8a1.6 1.6 0 0 1-2.3-2.3l7.4-7.4" />
                </svg>
              </button>
              <button type="button" className="composer-model">
                <span className="composer-model-dot" aria-hidden="true" />
                digichat · opus
              </button>
              <span className="composer-hint">
                <span className="kbd">/</span> commands
              </span>
            </div>

            <div className="composer-actions">
              <span className={`composer-count${value.length > MAX * 0.9 ? " warn" : ""}`}>
                {value.length}/{MAX}
              </span>
              <button
                type="button"
                className="composer-send"
                disabled={!value.trim()}
                aria-label="Send message"
                onClick={send}
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M7 12h11M13 6l6 6-6 6" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
