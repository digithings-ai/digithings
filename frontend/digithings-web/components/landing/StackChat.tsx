"use client";
import { useEffect, useRef, useState } from "react";
import { useStackChat } from "@/lib/useStackChat";
import { writeHandoff } from "@/lib/chatHandoff";

/**
 * "Ask about the stack" — the compact, single-shot quick-ask that lives in the
 * module manifest. It answers ONE question inline over the DigiVault docs (via the
 * shared `useStackChat` engine — no web search), then hands off: once a question
 * has been answered, the next one escalates to the full-screen DigiChat page,
 * carrying the transcript across tabs (see `writeHandoff`). This keeps the landing
 * terminal bounded — the inline thread is capped and the real session lives on
 * `/chat` — instead of growing the panel past the page (the old behaviour).
 *
 * Terminal aesthetic via the shared `.dt-*` / `.dtc-*` tokens; theme-aware and
 * keyboard accessible. Errors render as a friendly line, not a thrown thread.
 */
const SUGGESTIONS = ["What is digiquant?", "How does auth work?", "What does Olympus do?"];

export function StackChat() {
  const { messages, busy, error, send } = useStackChat();
  const [input, setInput] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  // Keep the newest tokens in view as they stream.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  const empty = messages.length === 0;
  // After the first completed exchange, a new question opens the full session.
  const escalateNext = messages.length >= 2 && !busy;

  function openFull(pending: string) {
    writeHandoff(messages, pending);
    window.open("/chat", "_blank", "noopener,noreferrer");
  }

  function submit(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    if (escalateNext) openFull(q);
    else void send(q);
    setInput("");
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    submit(input);
  }

  return (
    <div className="dtc">
      <div className="dtc-head">
        <span className="dt-mh-prompt">$</span> digithings ask
        <span className="dt-out-dim"> · quick question over the digivault</span>
        {!empty && (
          <button type="button" className="dtc-open" onClick={() => openFull("")}>
            open in digichat <span aria-hidden="true">↗</span>
          </button>
        )}
      </div>

      <div className="dtc-thread" ref={threadRef} aria-live="polite" aria-atomic="false">
        {empty && !error ? (
          <div className="dtc-empty">
            <p className="dt-out-dim">
              Ask one quick question about the stack — answers come only from the published
              docs. Follow-ups open a full session in digichat.
            </p>
            <div className="dtc-suggest">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="dtc-chip"
                  onClick={() => submit(s)}
                  disabled={busy}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ul className="dtc-msgs">
            {messages.map((m, i) => {
              const streaming = busy && m.role === "assistant" && i === messages.length - 1;
              return (
                <li key={i} className={`dtc-msg dtc-${m.role}`}>
                  <span className="dtc-who" aria-hidden="true">
                    {m.role === "user" ? ">" : "·"}
                  </span>
                  <span className="dtc-body">
                    {m.content}
                    {streaming && <span className="dt-cur" />}
                    {streaming && !m.content && <span className="dt-out-dim">retrieving…</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        {error && (
          <p className="dtc-error" role="alert">
            {error}
          </p>
        )}
      </div>

      {escalateNext && (
        <p className="dtc-escalate dt-out-dim">
          More questions? Your next one opens a full session in <strong>digichat</strong>.
        </p>
      )}

      <form className="dtc-form" onSubmit={onSubmit}>
        <span className="dt-mh-prompt" aria-hidden="true">
          $
        </span>
        <input
          className="dtc-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={escalateNext ? "ask a follow-up in digichat…" : "ask one quick question…"}
          aria-label="Ask one quick question about the digithings stack"
          disabled={busy}
          autoComplete="off"
          maxLength={500}
        />
        <button
          className="dtc-send"
          type="submit"
          disabled={busy || !input.trim()}
          aria-label={escalateNext ? "Open follow-up in digichat" : "Send question"}
        >
          {busy ? "…" : escalateNext ? "↗" : "↵"}
        </button>
      </form>
    </div>
  );
}
