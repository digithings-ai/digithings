"use client";
import { useEffect, useRef, useState } from "react";
import { useStackChat } from "@/lib/useStackChat";
import { readAndClearHandoff } from "@/lib/chatHandoff";
import { MiniMarkdown } from "@/lib/miniMarkdown";
import { CopyButton } from "@/lib/CopyButton";
import { DigiChatWordmark } from "@/components/DigiChatMark";
import { ChatActivities } from "@/components/ChatActivities";
import { ProviderSettings } from "@/components/ProviderSettings";
import { providerSummary, useProviderSettings } from "@/lib/providerSettings";

const INTRO = `digichat — the assistant for the digithings stack.

Ask about the architecture: how the modules fit together, how it's built, how it runs. I search digivault (the docs) before answering, so I cite real docs rather than guess.

Free tier uses OpenRouter's model pool — no key needed. Or bring your own key (OpenRouter, OpenAI, Anthropic, Gemini) for any model.

Try asking for a diagram of a pipeline.`;

const SUGGESTIONS = [
  "What does digigraph orchestrate?",
  "Diagram the digiquant backtest pipeline",
  "How does auth work in digikey?",
  "How is the stack built?",
];

export function DigiChatSession() {
  const provider = useProviderSettings();
  const { messages, busy, error, quotaPrompt, send, stop, seed, clearQuotaPrompt } =
    useStackChat([], provider);
  const [input, setInput] = useState("");
  const [intro, setIntro] = useState("");
  const [barOpen, setBarOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const openSettings = () => {
    clearQuotaPrompt();
    setSettingsOpen(true);
  };

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const h = readAndClearHandoff();
    if (h && (h.messages.length || h.pending)) {
      if (h.messages.length) seed(h.messages);
      setIntro(INTRO);
      if (h.pending) void send(h.pending);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setIntro(INTRO);
      return;
    }
    let i = 0;
    const step = Math.max(2, Math.ceil(INTRO.length / 110));
    const id = window.setInterval(() => {
      i += step;
      setIntro(INTRO.slice(0, i));
      if (i >= INTRO.length) window.clearInterval(id);
    }, 16);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy, intro, quotaPrompt]);

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
  const modelLabel = providerSummary(provider);

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
        <span className="dc-bar-meta">vault-grounded · agentic · streams live</span>
        <button type="button" className="dc-bar-key" onClick={openSettings}>
          {provider.isSet ? "key ✓" : "bring your own key"}
        </button>
        <span className="dc-bar-model">model: {modelLabel}</span>
      </div>

      <div className="dc-thread" ref={threadRef} aria-live="polite" aria-atomic="false">
        <div className="dc-msg dc-assistant dc-intro" aria-live="off">
          <span className="dc-who" aria-hidden="true">
            ·
          </span>
          <div className="dc-body dc-intro-body">
            {intro}
            {!introDone && <span className="dt-cur" />}
            {introDone && !provider.isSet ? (
              <p className="dc-intro-byok">
                {" "}
                <button type="button" className="dc-inline-link" onClick={openSettings}>
                  Bring your own API key
                </button>{" "}
                to use any provider.
              </p>
            ) : null}
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
                    {m.activities?.length ? <ChatActivities activities={m.activities} /> : null}
                    {m.content ? <MiniMarkdown text={m.content} /> : null}
                    {streaming && <span className="dt-cur" />}
                    {streaming && !m.content && !m.activities?.length ? (
                      <span className="dt-out-dim">connecting…</span>
                    ) : null}
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

        {quotaPrompt && !provider.isSet ? (
          <div className="dc-quota-banner" role="status">
            <p>
              Free tier quota may be exhausted.{" "}
              <button type="button" className="dc-inline-link" onClick={openSettings}>
                Continue with your own key
              </button>
            </p>
          </div>
        ) : null}

        {error && (
          <p className="dtc-error" role="alert">
            {error}
            {!provider.isSet ? (
              <>
                {" "}
                <button type="button" className="dc-inline-link" onClick={openSettings}>
                  Add your API key
                </button>
              </>
            ) : null}
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

      <ProviderSettings
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        apiKey={provider.apiKey}
        provider={provider.provider}
        model={provider.model}
        isSet={provider.isSet}
        onSave={provider.save}
        onClear={provider.clear}
      />
    </section>
  );
}
