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
  formatCliSettingLine,
  isLangCode,
  LANG_CHOICES,
  LANG_LABELS,
  matchingSlashCommands,
  nextPaletteIndex,
  parseSlashInput,
  slashHelpText,
  type CliSettingRow,
  type SlashDef,
} from "./slash-commands";
import {
  buildAnswerMailto,
  copyMarkdownWithFallback,
  downloadHtml,
  downloadMarkdown,
  downloadPlainText,
  openMailtoWithFallback,
  printTranscriptWithFallback,
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
  type TranscriptTurn,
} from "./transcript-markdown";
import type { DigiChatSessionProps, VaultHitSummary } from "./types";
import { useStreamingIntro } from "./useStreamingIntro";

const MAX_INPUT_LINES = 5;

type PaletteMode =
  | { kind: "commands" }
  | { kind: "choices"; command: SlashDef; options: readonly { value: string; label: string }[] };

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
  languageCode = "en",
  webSearchAllowed = false,
  webSearchEnabled = false,
  onWebSearchToggle,
}: DigiChatSessionProps) {
  const {
    messages,
    busy,
    error,
    quotaPrompt,
    send,
    stop,
    onRetry,
    regenerate,
    editLastUser,
    reset,
    providerIsSet = false,
    openSettings,
  } = chat;

  const [input, setInput] = useState("");
  const [localNotes, setLocalNotes] = useState<string[]>([]);
  const [openDoc, setOpenDoc] = useState<VaultHitSummary | null>(null);
  /** Index of the user turn being edited; only the latest user turn is eligible. */
  const [editingUserIndex, setEditingUserIndex] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [cliSettingsOpen, setCliSettingsOpen] = useState(false);
  const [cliSettingsIndex, setCliSettingsIndex] = useState(0);
  const [cliSettingsDiveId, setCliSettingsDiveId] = useState<string | null>(null);
  const [paletteMode, setPaletteMode] = useState<PaletteMode>({ kind: "commands" });
  const [paletteIndex, setPaletteIndex] = useState(0);
  const threadRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const editTaRef = useRef<HTMLTextAreaElement>(null);

  const introEnabled = showIntro && messages.length === 0 && !formReplacement;
  const { text: intro, done: introDone } = useStreamingIntro(welcomeIntro, introEnabled);
  const slashVisibility = { webSearch: webSearchAllowed, byok: showByok };
  const slashMatches =
    paletteMode.kind === "commands"
      ? matchingSlashCommands(input, slashVisibility)
      : [];
  const choiceRows =
    paletteMode.kind === "choices" ? paletteMode.options : ([] as readonly { value: string; label: string }[]);

  useEffect(() => {
    if (paletteMode.kind === "choices") return;
    setPaletteIndex(0);
  }, [input, paletteMode.kind]);

  useEffect(() => {
    if (!input.startsWith("/")) {
      setPaletteMode({ kind: "commands" });
    }
  }, [input]);

  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy, intro, quotaPrompt, formReplacement, localNotes, cliSettingsOpen]);

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

  /** Settled transcript: drop the in-flight assistant partial while busy (#3511). */
  function settledSessionMessages() {
    if (busy && messages.length > 0 && messages[messages.length - 1]?.role === "assistant") {
      return messages.slice(0, -1);
    }
    return messages;
  }

  function lastSettledAssistant() {
    const settled = settledSessionMessages();
    for (let i = settled.length - 1; i >= 0; i--) {
      const m = settled[i];
      if (m?.role === "assistant" && m.content.trim()) return m;
    }
    return null;
  }

  function settledSessionTurns(): TranscriptTurn[] {
    return settledSessionMessages()
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({
        role: m.role,
        content: m.content,
        sources:
          m.role === "assistant"
            ? citationHits(chainActivities(m.activities ?? [])).map((h) => ({
                title: h.title,
                path: h.path,
              }))
            : undefined,
      }));
  }

  function handleCopySlash() {
    const found = lastSettledAssistant();
    if (!found) {
      setLocalNotes((notes) => [...notes, "No assistant answer to copy yet."]);
      return;
    }
    const sources = citationHits(chainActivities(found.activities ?? [])).map((h) => ({
      title: h.title,
      path: h.path,
    }));
    const md = serializeAssistantMarkdown(found.content, sources);
    if (!md.trim()) {
      setLocalNotes((notes) => [...notes, "No assistant answer to copy yet."]);
      return;
    }
    void copyMarkdownWithFallback(md, { filename: "digichat-answer.md" }).then((result) => {
      const note =
        result === "clipboard"
          ? "Copied last answer to clipboard."
          : result === "download"
            ? "Clipboard blocked — saved last answer as digichat-answer.md."
            : result === "postMessage"
              ? "Copied last answer (parent frame)."
              : "Clipboard blocked — answer selected below, press ⌘C / ctrl+C.";
      setLocalNotes((notes) => [...notes, note]);
    });
  }

  function handleExportSlash(arg: string) {
    const sub = arg.trim().toLowerCase();
    if (sub && sub !== "last") {
      setLocalNotes((notes) => [...notes, "Use /export or /export last."]);
      return;
    }
    if (sub === "last") {
      const found = lastSettledAssistant();
      if (!found) {
        setLocalNotes((notes) => [...notes, "Nothing to export yet."]);
        return;
      }
      const sources = citationHits(chainActivities(found.activities ?? [])).map((h) => ({
        title: h.title,
        path: h.path,
      }));
      const md = serializeAssistantMarkdown(found.content, sources);
      if (!md.trim()) {
        setLocalNotes((notes) => [...notes, "Nothing to export yet."]);
        return;
      }
      try {
        downloadMarkdown("digichat-answer.md", md);
        setLocalNotes((notes) => [...notes, "Exported last answer as digichat-answer.md."]);
      } catch {
        setLocalNotes((notes) => [...notes, "Export failed in this browser."]);
      }
      return;
    }
    const md = serializeThreadMarkdown(settledSessionTurns());
    if (!md.trim()) {
      setLocalNotes((notes) => [...notes, "Nothing to export yet."]);
      return;
    }
    try {
      downloadMarkdown("digichat-thread.md", md);
      setLocalNotes((notes) => [...notes, "Exported thread as digichat-thread.md."]);
    } catch {
      setLocalNotes((notes) => [...notes, "Export failed in this browser."]);
    }
  }

  function openByok() {
    setCliSettingsOpen(false);
    openSettings?.();
  }

  function toggleWebSearchFromSlash() {
    if (!webSearchAllowed) {
      setLocalNotes((notes) => [
        ...notes,
        "Web search is not enabled for this tenant.",
      ]);
      return;
    }
    if (!onWebSearchToggle) {
      setLocalNotes((notes) => [...notes, "Web search cannot be changed here."]);
      return;
    }
    onWebSearchToggle();
    const next = !webSearchEnabled;
    setLocalNotes((notes) => [
      ...notes,
      `Web search ${next ? "on" : "off"} (External cites).`,
    ]);
  }

  function buildCliSettingRows(): CliSettingRow[] {
    const rows: CliSettingRow[] = [];
    if (webSearchAllowed) {
      rows.push({
        id: "websearch",
        label: "Web search",
        description: "Opt-in External cites when asking digichat",
        kind: "toggle",
        value: webSearchEnabled,
      });
    }
    rows.push({
      id: "lang",
      label: "Language",
      description: "Reply language presets — Up/Down to pick, Enter to set",
      kind: "choice",
      value: languageCode,
      options: LANG_CHOICES,
    });
    if (showByok) {
      rows.push({
        id: "byok",
        label: "BYOK",
        description: "Bring your own API key (also /byok)",
        kind: "action",
        actionLabel: providerIsSet ? "update key" : "configure",
      });
    }
    return rows;
  }

  function applyCliSetting(row: CliSettingRow) {
    if (row.kind === "toggle" && row.id === "websearch") {
      onWebSearchToggle?.();
      return;
    }
    if (row.kind === "choice" && row.id === "lang") {
      setCliSettingsDiveId("lang");
      setCliSettingsIndex(
        Math.max(
          0,
          LANG_CHOICES.findIndex((o) => o.value === languageCode),
        ),
      );
      return;
    }
    if (row.kind === "action" && row.id === "byok") {
      openByok();
    }
  }

  function selectLangChoice(code: string) {
    if (!isLangCode(code)) return;
    onLanguageChange?.(code);
    setLocalNotes((notes) => [...notes, `Language set to ${LANG_LABELS[code]}.`]);
    setPaletteMode({ kind: "commands" });
    setCliSettingsDiveId(null);
    clearComposer(taRef.current, setInput);
  }

  function activateSlashCommand(cmd: SlashDef) {
    if (cmd.id === "websearch") {
      toggleWebSearchFromSlash();
      clearComposer(taRef.current, setInput);
      setPaletteMode({ kind: "commands" });
      return;
    }
    if (cmd.id === "byok") {
      openByok();
      clearComposer(taRef.current, setInput);
      setPaletteMode({ kind: "commands" });
      return;
    }
    if (cmd.id === "settings") {
      setCliSettingsOpen(true);
      setCliSettingsIndex(0);
      setCliSettingsDiveId(null);
      clearComposer(taRef.current, setInput);
      setPaletteMode({ kind: "commands" });
      return;
    }
    if (cmd.choiceOptions?.length) {
      setPaletteMode({ kind: "choices", command: cmd, options: cmd.choiceOptions });
      setPaletteIndex(
        Math.max(
          0,
          cmd.choiceOptions.findIndex((o) => o.value === languageCode),
        ),
      );
      setInput(`${cmd.names[0]} `);
      taRef.current?.focus();
      return;
    }
    if (cmd.needsArg) {
      setInput(`${cmd.names[0]} `);
      setPaletteMode({ kind: "commands" });
      taRef.current?.focus();
      return;
    }
    submit(cmd.names[0]);
  }

  function submit(question: string) {
    const q = question.trim();
    if (!q) return;
    if (q.startsWith("/")) {
      const parsed = parseSlashInput(q);
      if (parsed.kind === "command" && parsed.command.id === "copy") {
        handleCopySlash();
        clearComposer(taRef.current, setInput);
        return;
      }
      if (parsed.kind === "command" && parsed.command.id === "export") {
        handleExportSlash(parsed.arg);
        clearComposer(taRef.current, setInput);
        return;
      }
      if (busy) return;
      if (parsed.kind === "incomplete") {
        if (parsed.command.choiceOptions?.length) {
          setPaletteMode({
            kind: "choices",
            command: parsed.command,
            options: parsed.command.choiceOptions,
          });
          setPaletteIndex(
            Math.max(
              0,
              parsed.command.choiceOptions.findIndex((o) => o.value === languageCode),
            ),
          );
        }
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
          setLocalNotes((notes) => [...notes, slashHelpText(slashVisibility)]);
          clearComposer(taRef.current, setInput);
          return;
        }
        if (parsed.command.id === "new") {
          reset?.();
          setLocalNotes([]);
          setOpenDoc(null);
          setCliSettingsOpen(false);
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
          setPaletteMode({ kind: "commands" });
          return;
        }
        if (parsed.command.id === "websearch") {
          toggleWebSearchFromSlash();
          clearComposer(taRef.current, setInput);
          return;
        }
        if (parsed.command.id === "byok") {
          if (!showByok) {
            setLocalNotes((notes) => [...notes, "BYOK is not available here."]);
          } else {
            openByok();
          }
          clearComposer(taRef.current, setInput);
          return;
        }
        if (parsed.command.id === "settings") {
          setCliSettingsOpen(true);
          setCliSettingsIndex(0);
          setCliSettingsDiveId(null);
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
    if (busy) return;
    void send(q);
    clearComposer(taRef.current, setInput);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (cliSettingsOpen) {
      const rows = buildCliSettingRows();
      if (cliSettingsDiveId === "lang") {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          setCliSettingsIndex((i) =>
            nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, LANG_CHOICES.length),
          );
          return;
        }
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          const choice = LANG_CHOICES[cliSettingsIndex];
          if (choice) selectLangChoice(choice.value);
          setCliSettingsDiveId(null);
          setCliSettingsIndex(
            Math.max(
              0,
              rows.findIndex((r) => r.id === "lang"),
            ),
          );
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setCliSettingsDiveId(null);
          return;
        }
      } else {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          setCliSettingsIndex((i) =>
            nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, rows.length),
          );
          return;
        }
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          const row = rows[cliSettingsIndex];
          if (row) applyCliSetting(row);
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setCliSettingsOpen(false);
          return;
        }
      }
    }

    if (paletteMode.kind === "choices" && choiceRows.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setPaletteIndex((i) =>
          nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, choiceRows.length),
        );
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const choice = choiceRows[paletteIndex];
        if (choice && paletteMode.command.id === "lang") {
          selectLangChoice(choice.value);
        }
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setPaletteMode({ kind: "commands" });
        return;
      }
    }

    if (paletteMode.kind === "commands" && slashMatches.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setPaletteIndex((i) =>
          nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, slashMatches.length),
        );
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const cmd = slashMatches[paletteIndex] ?? slashMatches[0];
        if (cmd) activateSlashCommand(cmd);
        return;
      }
    }

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  const handleOpenSettings = () => openByok();

  const panelBlocked = busy || !!settingsPanel || cliSettingsOpen;

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
  let lastAssistantIndex = -1;
  let lastUserIndex = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    const role = messages[i]?.role;
    if (lastAssistantIndex < 0 && role === "assistant") lastAssistantIndex = i;
    if (lastUserIndex < 0 && role === "user") lastUserIndex = i;
    if (lastAssistantIndex >= 0 && lastUserIndex >= 0) break;
  }
  const lastAssistant = lastAssistantIndex >= 0 ? messages[lastAssistantIndex] : undefined;
  const lastChain = lastAssistant ? chainActivities(lastAssistant.activities ?? []) : [];
  const showOptimisticSearch =
    busy && !waitingForAssistant && lastAssistant && lastChain.length === 0 && !lastAssistant.content;

  // Cancel in-progress edit if the transcript shifts or a run starts.
  useEffect(() => {
    if (editingUserIndex === null) return;
    if (!(busy || editingUserIndex !== lastUserIndex)) return;
    queueMicrotask(() => {
      setEditingUserIndex(null);
      setEditDraft("");
    });
  }, [busy, editingUserIndex, lastUserIndex]);

  const threadTurns: TranscriptTurn[] = messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({
      role: m.role,
      content: m.content,
      sources:
        m.role === "assistant"
          ? citationHits(chainActivities(m.activities ?? [])).map((h) => ({
              title: h.title,
              path: h.path,
            }))
          : undefined,
    }));
  const threadMarkdown = serializeThreadMarkdown(threadTurns);
  const canExportThread = threadMarkdown.trim().length > 0 && !busy;
  const canRegenerate =
    !!regenerate && !busy && lastAssistantIndex >= 0 && editingUserIndex === null;
  const canEditLastUser =
    !!editLastUser && !busy && lastUserIndex >= 0 && editingUserIndex === null;

  function beginEditLastUser(index: number) {
    if (!canEditLastUser || index !== lastUserIndex) return;
    setEditingUserIndex(index);
    setEditDraft(messages[index]?.content ?? "");
    queueMicrotask(() => editTaRef.current?.focus());
  }

  function cancelEdit() {
    setEditingUserIndex(null);
    setEditDraft("");
  }

  function submitEdit() {
    const next = editDraft.trim();
    if (!next || !editLastUser || editingUserIndex === null) return;
    setEditingUserIndex(null);
    setEditDraft("");
    void editLastUser(next);
  }

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
          const isLastAssistant = m.role === "assistant" && i === lastAssistantIndex;
          const isLastUser = m.role === "user" && i === lastUserIndex;
          const isEditing = editingUserIndex === i;
          const answerMarkdown =
            m.role === "assistant"
              ? serializeAssistantMarkdown(
                  m.content,
                  sources.map((h) => ({ title: h.title, path: h.path })),
                )
              : "";
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
                    {/* Copy on page + embed: clipboard first; embed falls back to
                        .md download / digichat:copy postMessage / textarea (#3465).
                        Print / mailto / txt / html reuse the same serializers
                        (#3510); print and mailto fall back to download when the
                        embed blocks them. Regen only when the controller opts in
                        (digigraph; #3466). */}
                    {!streaming && m.content ? (
                      <span className="dc-msg-actions">
                        <CopyButton
                          text={answerMarkdown}
                          className="dc-msg-copy"
                          ariaLabel="Copy answer as markdown"
                          filename="digichat-answer.md"
                        />
                        <button
                          type="button"
                          className="dc-msg-copy"
                          aria-label="Email answer"
                          title={
                            layout === "embed"
                              ? "Downloads .md in embed (mail clients are often blocked in iframes)"
                              : "Opens your mail client with the answer (truncated to fit); falls back to download"
                          }
                          onClick={() =>
                            openMailtoWithFallback(buildAnswerMailto(answerMarkdown), {
                              fallbackMarkdown: answerMarkdown,
                              fallbackFilename: "digichat-answer.md",
                              preferDownload: layout === "embed",
                            })
                          }
                        >
                          mail
                        </button>
                        {i === messages.length - 1 && canExportThread ? (
                          <>
                            <button
                              type="button"
                              className="dc-msg-copy"
                              aria-label="Download thread as markdown"
                              onClick={() =>
                                downloadMarkdown("digichat-thread.md", threadMarkdown)
                              }
                            >
                              md
                            </button>
                            <button
                              type="button"
                              className="dc-msg-copy"
                              aria-label="Download thread as text"
                              onClick={() =>
                                downloadPlainText("digichat-thread.txt", threadMarkdown)
                              }
                            >
                              txt
                            </button>
                            <button
                              type="button"
                              className="dc-msg-copy"
                              aria-label="Download thread as html"
                              onClick={() =>
                                downloadHtml("digichat-thread.html", threadMarkdown)
                              }
                            >
                              html
                            </button>
                            <button
                              type="button"
                              className="dc-msg-copy"
                              aria-label="Print transcript"
                              title={
                                layout === "embed"
                                  ? "Downloads .md in embed (print is often blocked in iframes)"
                                  : "Opens print preview (Save as PDF); falls back to download"
                              }
                              onClick={() =>
                                printTranscriptWithFallback({
                                  fallbackMarkdown: threadMarkdown,
                                  fallbackFilename: "digichat-thread.md",
                                  preferDownload: layout === "embed",
                                })
                              }
                            >
                              print
                            </button>
                          </>
                        ) : null}
                        {isLastAssistant && regenerate ? (
                          <button
                            type="button"
                            className="dc-msg-copy"
                            aria-label="Regenerate answer"
                            disabled={!canRegenerate}
                            title="Replays the full digigraph workflow on this session"
                            onClick={() => regenerate()}
                          >
                            regen
                          </button>
                        ) : null}
                      </span>
                    ) : null}
                    {streaming && m.content ? <ChatStreamCursor className="dt-cur" /> : null}
                  </>
                ) : isEditing ? (
                  <div className="dc-edit-last">
                    <textarea
                      ref={editTaRef}
                      className="dc-edit-textarea"
                      value={editDraft}
                      onChange={(e) => setEditDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Escape") {
                          e.preventDefault();
                          cancelEdit();
                        } else if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          submitEdit();
                        }
                      }}
                      aria-label="Edit last message"
                      rows={3}
                      maxLength={2000}
                    />
                    <span className="dc-msg-actions dc-msg-actions-visible">
                      <button
                        type="button"
                        className="dc-msg-copy"
                        disabled={!editDraft.trim()}
                        onClick={submitEdit}
                      >
                        save
                      </button>
                      <button type="button" className="dc-msg-copy" onClick={cancelEdit}>
                        cancel
                      </button>
                    </span>
                  </div>
                ) : (
                  <>
                    {m.content}
                    {isLastUser && editLastUser ? (
                      <span className="dc-msg-actions">
                        <button
                          type="button"
                          className="dc-msg-copy"
                          aria-label="Edit last message"
                          disabled={!canEditLastUser}
                          title="Replaces this turn and replays the digigraph workflow"
                          onClick={() => beginEditLastUser(i)}
                        >
                          edit
                        </button>
                      </span>
                    ) : null}
                  </>
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
                Continue with your own key (/byok)
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
                  {providerIsSet ? "Update your API key (/byok)" : "Add your API key (/byok)"}
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

        {cliSettingsOpen ? (
          <div className="dc-msg dc-assistant" role="dialog" aria-label="Settings">
            <span className="dc-who" aria-hidden="true">
              ·
            </span>
            <div className="dc-body dc-slash-note dc-cli-settings">
              <pre>
                {(() => {
                  const rows = buildCliSettingRows();
                  if (cliSettingsDiveId === "lang") {
                    return [
                      "settings › language",
                      ...LANG_CHOICES.map((o, i) =>
                        `${i === cliSettingsIndex ? ">" : " "} ${o.value} — ${o.label}`,
                      ),
                      "",
                      "Up/Down select · Enter set · Esc back",
                    ].join("\n");
                  }
                  return [
                    "settings",
                    ...rows.map((row, i) => formatCliSettingLine(row, i === cliSettingsIndex)),
                    "",
                    "Up/Down navigate · Enter flip/open · Esc close · /byok for keys",
                  ].join("\n");
                })()}
              </pre>
            </div>
          </div>
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
            if (paletteMode.kind === "choices" && choiceRows.length) {
              const choice = choiceRows[paletteIndex];
              if (choice && paletteMode.command.id === "lang") {
                selectLangChoice(choice.value);
              }
              return;
            }
            if (slashMatches.length) {
              const cmd = slashMatches[paletteIndex] ?? slashMatches[0];
              if (cmd) activateSlashCommand(cmd);
              return;
            }
            submit(input);
          }}
        >
          {paletteMode.kind === "choices" && choiceRows.length ? (
            <ul className="dc-slash" role="listbox" aria-label="Language presets">
              {choiceRows.map((opt, i) => (
                <li key={opt.value}>
                  <button
                    type="button"
                    className={`dc-slash-item${i === paletteIndex ? " dc-slash-item-active" : ""}`}
                    aria-selected={i === paletteIndex}
                    onMouseEnter={() => setPaletteIndex(i)}
                    onClick={() => {
                      if (paletteMode.command.id === "lang") selectLangChoice(opt.value);
                    }}
                  >
                    <span className="dc-slash-cmd">{opt.value}</span>
                    <span className="dc-slash-hint">{opt.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : slashMatches.length ? (
            <ul className="dc-slash" role="listbox" aria-label="Slash commands">
              {slashMatches.map((cmd, i) => (
                <li key={cmd.id}>
                  <button
                    type="button"
                    className={`dc-slash-item${i === paletteIndex ? " dc-slash-item-active" : ""}`}
                    aria-selected={i === paletteIndex}
                    onMouseEnter={() => setPaletteIndex(i)}
                    onClick={() => activateSlashCommand(cmd)}
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
            disabled={panelBlocked && !cliSettingsOpen}
          />
          {busy && stop ? (
            <button type="button" className="dc-stop" onClick={stop} aria-label="Stop generating">
              stop
            </button>
          ) : (
            <button
              type="submit"
              className="dc-send"
              disabled={(!input.trim() && !slashMatches.length && paletteMode.kind !== "choices") || panelBlocked}
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
