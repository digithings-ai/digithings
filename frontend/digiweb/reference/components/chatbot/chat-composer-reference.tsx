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

      <div className="chat-surface mt-[1.3rem] max-w-[760px] flex flex-col gap-[0.7rem] rounded-[12px] border border-term-hair bg-term-bg px-[1.15rem] pt-[1rem] pb-[1.2rem] font-mono">
        {sent ? (
          <div className="flex gap-[0.55rem] items-baseline justify-start">
            <div className="chat-bubble--user min-w-0 border-0 bg-transparent p-0 font-mono text-[0.84rem] leading-[1.6] text-term-ink">
              {sent}
            </div>
          </div>
        ) : null}

        <div className="composer border border-hair rounded-[14px] bg-surface px-[0.85rem] pt-[0.75rem] pb-[0.6rem]">
          <textarea
            ref={areaRef}
            className="composer-input w-full border-0 bg-transparent resize-none text-ink font-sans text-[0.9rem] leading-[1.5] outline-none min-h-[1.5rem]"
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

          <div className="composer-tray flex items-center justify-between gap-[0.75rem] mt-[0.5rem]">
            <div className="composer-tools flex items-center gap-[0.5rem] min-w-0">
              <button
                type="button"
                className="composer-icon inline-flex p-[0.35rem] border-0 bg-transparent text-ink-mute cursor-pointer"
                aria-label="Attach a file"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.5 12.5 21a5 5 0 0 1-7-7l8-8a3.3 3.3 0 0 1 4.7 4.7l-8 8a1.6 1.6 0 0 1-2.3-2.3l7.4-7.4" />
                </svg>
              </button>
              <button
                type="button"
                className="composer-model inline-flex items-center gap-[0.4rem] px-[0.6rem] py-[0.28rem] border border-hair rounded-full bg-transparent text-ink-soft font-mono text-[0.68rem] cursor-pointer"
              >
                <span className="size-1.5 rounded-full bg-accent" aria-hidden="true" />
                digichat · opus
              </button>
              <span className="inline-flex items-center gap-[0.35rem] text-ink-mute font-mono text-[0.66rem]">
                <span className="kbd">/</span> commands
              </span>
            </div>

            <div className="flex items-center gap-[0.6rem] shrink-0">
              <span
                className={`font-mono text-[0.62rem] tabular-nums ${value.length > MAX * 0.9 ? "text-down" : "text-ink-mute"}`}
              >
                {value.length}/{MAX}
              </span>
              <button
                type="button"
                className="composer-send inline-flex items-center justify-center w-8 h-8 border-0 rounded-full bg-accent cursor-pointer"
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
