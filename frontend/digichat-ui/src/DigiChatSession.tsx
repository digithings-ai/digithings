"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ChatStreamCursor, ChatToolCall } from "@digithings/web";
import {
  stripFoundryCitationMarkers,
  chainActivities,
  citationHits,
} from "./activity-view";
import { ChatActivities } from "./components/ChatActivities";
import { CopyButton } from "./components/CopyButton";
import { DigiChatWordmark } from "./components/DigiChatMark";
import { DocumentPane } from "./components/DocumentPane";
import { MiniMarkdown } from "./components/MiniMarkdown";
import {
  isLangCode,
  LANG_LABELS,
  matchingSlashCommands,
  parseSlashInput,
  slashHelpText,
} from "./slash-commands";
import type { DigiChatSessionProps, VaultHitSummary } from "./types";
import { useStreamingIntro } from "./useStreamingIntro";

const MAX_INPUT_LINES = 5;

function clearComposer(ta: HTMLTextAreaElement | null, setInput: (v: string) => void) {
  setInput("");
  if (ta) {
    ta.style.height = "auto";
    ta.style.overflowY = "hidden";
  }
}

export function DigiChatSession({
  welcomeIntro,
  suggestions = [],
  placeholder,
  showByok,
  /** When false, error rows omit the inline BYOK link (ungated dogfood / infra errors). */
  showByokOnError = true,
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
  onLanguageChange,
}: DigiChatSessionProps) {
  const {
    messages,
    busy,
    error,
    quotaPrompt,
    send,
    stop,
    onRetry,
    reset,
    providerIsSet = false,
    openSettings,
  } = chat;

  const [input, setInput] = useState("");
  const [localNotes, setLocalNotes] = useState<string[]>([]);
  const [openDoc, setOpenDoc] = useState<VaultHitSummary | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const introEnabled = showIntro && messages.length === 0 && !formReplacement;
  const { text: intro, done: introDone } = useStreamingIntro(welcomeIntro, introEnabled);
  const slashMatches = matchingSlashCommands(input);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy, intro, quotaPrompt, formReplacement, localNotes]);

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
    if (q.startsWith("/")) {
      const parsed = parseSlashInput(q);
      if (parsed.kind === "incomplete") {
        setInput(parsed.prefix);
        return;
      }
      if (parsed.kind === "unknown") {
        setLocalNotes((notes) => [...notes, `Unknown command \`${parsed.name}\`. Type /help.`]);
        clearComposer(taRef.current, setInput);
        return;
      }
      if (parsed.kind === "command") {
        if (parsed.command.id === "help") {
          setLocalNotes((notes) => [...notes, slashHelpText()]);
          clearComposer(taRef.current, setInput);
          return;
        }
        if (parsed.command.id === "new") {
          reset?.();
          setLocalNotes([]);
          setOpenDoc(null);
          clearComposer(taRef.current, setInput);
          return;
        }
        if (parsed.command.id === "lang") {
          const code = parsed.arg.trim().toLowerCase();
          if (!isLangCode(code)) {
            setLocalNotes((notes) => [...notes, "Use /lang en, de, it, es, or fr."]);
          } else {
            onLanguageChange?.(code);
            setLocalNotes((notes) => [...notes, `Language set to ${LANG_LABELS[code]}.`]);
          }
          clearComposer(taRef.current, setInput);
          return;
        }
        if (parsed.command.forceTool) {
          void send(parsed.arg, { forceTool: parsed.command.forceTool });
          clearComposer(taRef.current, setInput);
          return;
        }
      }
    }
    void send(q);
    clearComposer(taRef.current, setInput);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  const handleOpenSettings = () => openSettings?.();

  const sessionClass = [
    "dc-session",
    layout === "embed" ? "dc-session-embed" : "",
    openDoc ? "dc-session-with-pane" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  const renderAssistant = (content: string, streaming: boolean) => {
    const clean = stripFoundryCitationMarkers(content);
    if (renderAssistantContent) return renderAssistantContent(clean, streaming);
    if (!clean) return null;
    return <MiniMarkdown text={clean} />;
  };

  const waitingForAssistant =
    busy && (messages.length === 0 || messages[messages.length - 1]?.role === "user");
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const lastChain = lastAssistant ? chainActivities(lastAssistant.activities ?? []) : [];
  const showOptimisticSearch =
    busy && !waitingForAssistant && lastAssistant && lastChain.length === 0 && !lastAssistant.content;

  return (
    <section className={sessionClass} aria-label={ariaLabel}>
      {headerSlot ??
        (branding?.title ? null : (
          <header className="dc-wordmark-header">
            <DigiChatWordmark />
          </header>
        ))}

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

      <div className="dc-session-main">
      <div className="dc-thread" ref={threadRef} aria-live="polite" aria-atomic="false">
        {introEnabled && welcomeIntro ? (
          <div className="dc-msg dc-assistant dc-intro" aria-live="off">
            <span className="dc-who" aria-hidden="true">
              ·
            </span>
            <div className="dc-body dc-intro-body">
              {intro}
              {!introDone && <ChatStreamCursor className="dt-cur" />}
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
          const chain = chainActivities(m.activities ?? []);
          const sources = m.role === "assistant" && !streaming ? citationHits(chain) : [];
          const emptyWait = streaming && chain.length === 0 && !m.content;
          return (
            <div key={i} className={`dc-msg dc-${m.role}`}>
              <span className="dc-who" aria-hidden="true">
                {m.role === "user" ? ">" : "·"}
              </span>
              <div className="dc-body">
                {m.role === "assistant" ? (
                  <>
                    {chain.length ? (
                      <ChatActivities activities={chain} onOpenSource={setOpenDoc} />
                    ) : emptyWait || (showOptimisticSearch && i === messages.length - 1) ? (
                      <ChatToolCall name="Searching…" status="running" lines={["Searching…"]} />
                    ) : null}
                    {renderAssistant(m.content, streaming)}
                    {sources.length ? (
                      <ul className="dc-source-cards">
                        {sources.map((hit) => (
                          <li key={hit.path}>
                            <button
                              type="button"
                              className="dc-source-card"
                              onClick={() => setOpenDoc(hit)}
                            >
                              <span className="dc-source-card-title">{hit.title}</span>
                              {hit.path && hit.path !== hit.title ? (
                                <span className="dc-source-card-path">{hit.path}</span>
                              ) : null}
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {/* No copy on embed: clipboard API is blocked in the
                        cross-origin iframe, so the button would silently no-op. */}
                    {layout !== "embed" && !streaming && m.content ? (
                      <CopyButton
                        text={stripFoundryCitationMarkers(m.content)}
                        className="dc-msg-copy"
                        ariaLabel="Copy answer"
                      />
                    ) : null}
                    {streaming && m.content ? <ChatStreamCursor className="dt-cur" /> : null}
                  </>
                ) : (
                  m.content
                )}
              </div>
            </div>
          );
        })}

        {waitingForAssistant ? (
          <div className="dc-msg dc-assistant" aria-busy="true">
            <span className="dc-who" aria-hidden="true">
              ·
            </span>
            <div className="dc-body">
              <ChatToolCall name="Searching…" status="running" lines={["Searching…"]} />
            </div>
          </div>
        ) : null}

        {localNotes.map((note, i) => (
          <div key={`note-${i}`} className="dc-msg dc-assistant">
            <span className="dc-who" aria-hidden="true">
              ·
            </span>
            <div className="dc-body dc-slash-note">
              <pre>{note}</pre>
            </div>
          </div>
        ))}

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
            {showByok && showByokOnError ? (
              <>
                {" "}
                <button type="button" className="dc-inline-link" onClick={handleOpenSettings}>
                  {providerIsSet ? "Update your API key" : "Add your API key"}
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

        {settingsPanel}
      </div>
      {openDoc ? <DocumentPane hit={openDoc} onClose={() => setOpenDoc(null)} /> : null}
      </div>

      {formReplacement ?? (
        <form
          className="dc-form"
          onSubmit={(e) => {
            e.preventDefault();
            submit(input);
          }}
        >
          {slashMatches.length ? (
            <ul className="dc-slash" role="listbox" aria-label="Slash commands">
              {slashMatches.map((cmd) => (
                <li key={cmd.id}>
                  <button
                    type="button"
                    className="dc-slash-item"
                    onClick={() => {
                      setInput(cmd.needsArg ? `${cmd.names[0]} ` : cmd.names[0]);
                      taRef.current?.focus();
                    }}
                  >
                    <span className="dc-slash-cmd">{cmd.names[0]}</span>
                    <span className="dc-slash-hint">{cmd.hint}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
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
            disabled={busy || !!settingsPanel}
          />
          {busy && stop ? (
            <button type="button" className="dc-stop" onClick={stop} aria-label="Stop generating">
              stop
            </button>
          ) : (
            <button
              type="submit"
              className="dc-send"
              disabled={!input.trim() || busy || !!settingsPanel}
              aria-label="Send message"
            >
              ↵
            </button>
          )}
        </form>
      )}

      {footerSlot}
    </section>
  );
}
