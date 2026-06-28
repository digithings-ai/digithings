"use client";
import { useEffect, useRef, useState } from "react";
import { useStackChat } from "@/lib/useStackChat";
import { readAndClearHandoff } from "@/lib/chatHandoff";
import { MiniMarkdown } from "@/lib/miniMarkdown";
import { CopyButton } from "@/lib/CopyButton";
import { DigiChatMark, DigiChatWordmark } from "@/components/DigiChatMark";

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
const INTRO = `Hi — I'm DigiChat, the assistant for the DigiThings stack.

I answer questions about the architecture: how the modules fit together, how the system is built, and how it runs. Ask me anything — DigiGraph orchestration, DigiQuant backtests, auth in DigiKey, retrieval in DigiSearch — the lot.

A bit about me: I'm grounded in DigiVault, a self-hosted, Obsidian-style vault in the cloud, and I search it before every answer, so I cite the real docs instead of guessing. I run on OpenRouter's free model pool — no sign-up, no key needed. For heavier use or stronger models, bring-your-own-key is coming soon.

Where should we start?`;

const SUGGESTIONS = [
  "What does DigiGraph orchestrate?",
  "How does auth work?",
  "How are you built?",
  "What can I do with DigiQuant?",
];

export function DigiChatSession() {
  const { messages, busy, error, send, stop, seed } = useStackChat();
  const [input, setInput] = useState("");
  const [intro, setIntro] = useState(""); // typed-out self-introduction
  const threadRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Resume a landing handoff, else type out the self-intro. The intro reveal drives
  // `intro` as an animation, so synchronous setState in the effect body is intentional.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const h = readAndClearHandoff();
    if (h && h.messages.length) {
      seed(h.messages);
      setIntro(INTRO); // show intro instantly above a resumed thread
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
    <section className="dc-session" aria-label="DigiChat">
      <div className="dc-bar">
        <DigiChatMark size={18} />
        <DigiChatWordmark />
        <span className="dc-bar-meta">· flagship assistant · vault-grounded</span>
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
        <span className="dt-mh-prompt" aria-hidden="true">
          $
        </span>
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
          aria-label="Ask DigiChat"
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
