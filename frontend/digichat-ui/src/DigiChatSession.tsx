"use client";

import { useEffect, useRef, useState } from "react";
import { ChatActivities } from "./components/ChatActivities";
import { CopyButton } from "./components/CopyButton";
import { DigiChatWordmark } from "./components/DigiChatMark";
import { MiniMarkdown } from "./components/MiniMarkdown";
import type { DigiChatSessionProps } from "./types";
import { useStreamingIntro } from "./useStreamingIntro";

const MAX_INPUT_LINES = 5;

export function DigiChatSession({
  welcomeIntro,
  suggestions = [],
  placeholder,
  showByok,
  showStatusBar = false,
  branding,
  ariaLabel = "digichat",
  className,
  layout = "page",
  chat,
  headerSlot,
  footerSlot,
  formReplacement,
  settingsPanel,
  renderAssistantContent,
  showIntro = true,
}: DigiChatSessionProps) {
  const {
    messages,
    busy,
    error,
    quotaPrompt,
    send,
    stop,
    onRetry,
    modelLabel,
    providerIsSet = false,
    openSettings,
  } = chat;

  const [input, setInput] = useState("");
  const [barOpen, setBarOpen] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const introEnabled = showIntro && messages.length === 0 && !formReplacement;
  const { text: intro, done: introDone } = useStreamingIntro(welcomeIntro, introEnabled);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy, intro, quotaPrompt, formReplacement]);

  function resizeTextarea(ta: HTMLTextAreaElement) {
    const style = getComputedStyle(ta);
    const lineHeight = parseFloat(style.lineHeight) || 21;
    const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const maxHeight = lineHeight * MAX_INPUT_LINES + padding;
    ta.style.height = "0px";
    const next = Math.min(ta.scrollHeight, maxHeight);
    ta.style.height = `${next}px`;
    ta.style.overflowY = ta.scrollHeight > maxHeight ? "auto" : "hidden";
  }

  function submit(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    void send(q);
    setInput("");
    if (taRef.current) {
      taRef.current.style.height = "auto";
      taRef.current.style.overflowY = "hidden";
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  const handleOpenSettings = () => openSettings?.();

  const sessionClass = [
    "dc-session",
    layout === "embed" ? "dc-session-embed" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  const renderAssistant = (content: string, streaming: boolean) => {
    if (renderAssistantContent) return renderAssistantContent(content, streaming);
    if (!content) return null;
    return <MiniMarkdown text={content} />;
  };

  return (
    <section className={sessionClass} aria-label={ariaLabel}>
      {headerSlot}

      {branding?.title ? (
        <header className="dc-brand">
          <span>{branding.title}</span>
          {branding.attributionUrl ? (
            <span className="dc-brand-by">
              (
              <a
                href={branding.attributionUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="dc-brand-link"
              >
                {branding.attributionLabel ?? "by digichat"}
              </a>
              )
            </span>
          ) : null}
        </header>
      ) : null}

      {showStatusBar ? (
        <>
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
            {showByok ? (
              <button type="button" className="dc-bar-key" onClick={handleOpenSettings}>
                {providerIsSet ? "key ✓" : "bring your own key"}
              </button>
            ) : null}
            {modelLabel ? <span className="dc-bar-model">model: {modelLabel}</span> : null}
          </div>
        </>
      ) : null}

      <div className="dc-thread" ref={threadRef} aria-live="polite" aria-atomic="false">
        {introEnabled && welcomeIntro ? (
          <div className="dc-msg dc-assistant dc-intro" aria-live="off">
            <span className="dc-who" aria-hidden="true">
              ·
            </span>
            <div className="dc-body dc-intro-body">
              {intro}
              {!introDone && <span className="dt-cur" />}
              {introDone && showByok && !providerIsSet ? (
                <p className="dc-intro-byok">
                  {" "}
                  <button type="button" className="dc-inline-link" onClick={handleOpenSettings}>
                    Bring your own API key
                  </button>{" "}
                  to use any provider.
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        {introDone && messages.length === 0 && suggestions.length > 0 && (
          <div className="dc-suggest">
            {suggestions.map((s) => (
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
                    {renderAssistant(m.content, streaming)}
                    {streaming && <span className="dt-cur" />}
                    {streaming && !m.content && !m.activities?.length ? (
                      <span className="dc-out-dim">connecting…</span>
                    ) : null}
                  </>
                ) : (
                  m.content
                )}
              </div>
              {m.role === "assistant" && !streaming && m.content ? (
                <CopyButton text={m.content} className="dc-msg-copy" ariaLabel="Copy answer" />
              ) : null}
            </div>
          );
        })}

        {showByok && quotaPrompt && !providerIsSet ? (
          <div className="dc-quota-banner" role="status">
            <p>
              Free tier quota may be exhausted.{" "}
              <button type="button" className="dc-inline-link" onClick={handleOpenSettings}>
                Continue with your own key
              </button>
            </p>
          </div>
        ) : null}

        {error ? (
          <p className="dtc-error" role="alert">
            {error}
            {showByok && !providerIsSet ? (
              <>
                {" "}
                <button type="button" className="dc-inline-link" onClick={handleOpenSettings}>
                  Add your API key
                </button>
              </>
            ) : null}
            {onRetry ? (
              <>
                {" "}
                <button type="button" className="dc-inline-link" onClick={onRetry}>
                  Retry
                </button>
              </>
            ) : null}
          </p>
        ) : null}
      </div>

      {formReplacement ?? (
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
              resizeTextarea(e.target);
            }}
            onKeyDown={onKeyDown}
            placeholder={placeholder}
            aria-label={placeholder}
            rows={1}
            maxLength={2000}
            disabled={busy}
          />
          {busy && stop ? (
            <button type="button" className="dc-stop" onClick={stop} aria-label="Stop generating">
              stop
            </button>
          ) : (
            <button
              type="submit"
              className="dc-send"
              disabled={!input.trim() || busy}
              aria-label="Send message"
            >
              ↵
            </button>
          )}
        </form>
      )}

      {footerSlot}
      {settingsPanel}
    </section>
  );
}
