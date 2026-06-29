"use client";
import { useEffect, useRef, useState } from "react";
import { useStackChat } from "@/lib/useStackChat";
import { readAndClearHandoff } from "@/lib/chatHandoff";
import { MiniMarkdown } from "@/lib/miniMarkdown";
import { CopyButton } from "@/lib/CopyButton";
import { DigiChatWordmark } from "@/components/DigiChatMark";

/**
 * DigiChatSession — the full-screen signature DigiChat experience on `/chat`.
 * A terminal-skinned chat with the features you expect from a real one (markdown,
 * copy code, multi-line input, stop), on the shared `useStackChat` engine.
 *
 * It opens with a streamed self-introduction (client-side, display-only — never
 * sent upstream, so it's instant, free, and always on-message) that doubles as the
 * page's marketing. If the visitor arrived from the landing quick-ask, it resumes
 * that session via the cross-tab handoff (see `chatHandoff`).
 *
 * Theme-aware via the design tokens (not hardcoded dark), consistent with the
 * module manifest.
 */
const INTRO = `digichat — the assistant for the digithings stack.

Ask about the architecture: how the modules fit together, how it's built, how it runs. I search digivault (the docs) before answering, so I cite real docs rather than guess. Running on OpenRouter's free model pool — no key needed.

Try asking for a diagram of a pipeline.`;

const SUGGESTIONS = [
  "What does digigraph orchestrate?",
  "Diagram the digiquant backtest pipeline",
  "How does auth work in digikey?",
  "How is the stack built?",
];

export function DigiChatSession() {
  const { messages, busy, error, send, stop, seed } = useStackChat();
  const [input, setInput] = useState("");
  const [intro, setIntro] = useState(""); // typed-out self-introduction
  const [barOpen, setBarOpen] = useState(false); // retractable status bar (off by default)
  const threadRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Resume a landing handoff, else type out the self-intro. The intro reveal drives
  // `intro` as an animation, so synchronous setState in the effect body is intentional.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const h = readAndClearHandoff();
    // A handoff may carry a prior transcript (landing quick-ask) OR just a pending
    // question with no history (the per-module "ask digichat" shortcut). Honor both.
    if (h && (h.messages.length || h.pending)) {
      if (h.messages.length) seed(h.messages);
      setIntro(INTRO); // show intro instantly above the seeded/asked thread
      if (h.pending) void send(h.pending);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setIntro(INTRO);
      return;
    }
    let i = 0;
    const step = Math.max(2, Math.ceil(INTRO.length / 110)); // ~1.8s regardless of length
    const id = window.setInterval(() => {
      i += step;
      setIntro(INTRO.slice(0, i));
      if (i >= INTRO.length) window.clearInterval(id);
    }, 16);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Keep the newest content in view as it streams.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy, intro]);

  function submit(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    void send(q);
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  const introDone = intro.length >= INTRO.length;

  return (
    <section className="dc-session" aria-label="digichat">
      <button
        type="button"
        className="dc-bar-toggle"
        aria-expanded={barOpen}
        onClick={() => setBarOpen((v) => !v)}
      >
        <DigiChatWordmark /> {barOpen ? "▾" : "▸"}
      </button>
      <div className={`dc-bar${barOpen ? "" : " is-collapsed"}`} aria-hidden={!barOpen}>
        <span className="dc-bar-meta">vault-grounded · searches digivault before answering</span>
        <span className="dc-bar-model">model: free pool</span>
      </div>

      <div className="dc-thread" ref={threadRef} aria-live="polite" aria-atomic="false">
        <div className="dc-msg dc-assistant dc-intro" aria-live="off">
          <span className="dc-who" aria-hidden="true">
            ·
          </span>
          <div className="dc-body">
            {intro}
            {!introDone && <span className="dt-cur" />}
          </div>
        </div>

        {introDone && messages.length === 0 && (
          <div className="dc-suggest">
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
        )}

        {messages.map((m, i) => {
          const streaming = busy && m.role === "assistant" && i === messages.length - 1;
          return (
            <div key={i} className={`dc-msg dc-${m.role}`}>
              <span className="dc-who" aria-hidden="true">
                {m.role === "user" ? ">" : "·"}
              </span>
              <div className="dc-body">
                {m.role === "assistant" ? (
                  <>
                    <MiniMarkdown text={m.content} />
                    {streaming && <span className="dt-cur" />}
                    {streaming && !m.content && <span className="dt-out-dim">retrieving…</span>}
                  </>
                ) : (
                  m.content
                )}
              </div>
              {m.role === "assistant" && !streaming && m.content && (
                <CopyButton text={m.content} className="dc-msg-copy" ariaLabel="Copy answer" />
              )}
            </div>
          );
        })}

        {error && (
          <p className="dtc-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <form
        className="dc-form"
        onSubmit={(e) => {
          e.preventDefault();
          submit(input);
        }}
      >
        <textarea
          ref={taRef}
          className="dc-textarea"
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(140, e.target.scrollHeight)}px`;
          }}
          onKeyDown={onKeyDown}
          placeholder="ask digichat anything…   (enter to send · shift+enter for a new line)"
          aria-label="Ask digichat"
          rows={1}
          maxLength={2000}
        />
        {busy ? (
          <button type="button" className="dc-stop" onClick={stop} aria-label="Stop generating">
            stop
          </button>
        ) : (
          <button
            type="submit"
            className="dc-send"
            disabled={!input.trim()}
            aria-label="Send message"
          >
            ↵
          </button>
        )}
      </form>
    </section>
  );
}
