"use client";

/**
 * CLI-skinned assistant-ui thread + composer.
 * Uses existing .dc-* / .app-input session tokens — not stock ChatGPT chrome.
 */
import { useCallback, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { useAISDKChat } from "@assistant-ui/ai-sdk";
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import type { UIMessage } from "ai";
import {
  matchingSlashCommands,
  nextPaletteIndex,
  parseSlashInput,
  slashHelpText,
  serializeAssistantMarkdown,
  serializeThreadMarkdown,
  copyMarkdownWithFallback,
  downloadMarkdown,
  type SlashVisibility,
} from "@digithings/digichat-ui";
import { Button } from "@/components/ui/button";
import { messageSourceCitations } from "@/lib/message-sources";
import { cn } from "@/lib/utils";
import { LegacyActivityHydrate, messagePlainText } from "./cli-message-body";
import { cliMessagePartComponents, UiMessageParts } from "./cli-message-parts";

export type CliThreadProps = {
  emptyHint?: ReactNode;
  headerSlot?: ReactNode;
  footerSlot?: ReactNode;
  /** Rendered under the transcript, above the slash palette (e.g. quant strip). */
  belowViewportSlot?: ReactNode;
  formReplacement?: ReactNode;
  suggestions?: readonly string[];
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  layout?: "page" | "embed";
  slashVisibility?: SlashVisibility;
  extraSlash?: ReadonlyArray<{ cmd: string; hint: string }>;
  /** Return true if the command was fully handled. */
  onSlashCommand?: (raw: string) => boolean;
  /**
   * Embed/auth intercept. Return true to skip the runtime send
   * (caller already sent or blocked for a gate).
   */
  onSendRequest?: (text: string, opts?: { forceTool?: string }) => boolean | void;
  onOpenSettings?: () => void;
  /** If set, /byok calls this instead of onOpenSettings. */
  onByok?: () => void;
  onLanguageChange?: (code: string) => void;
  /** Called for /new instead of only clearing the client transcript. */
  onReset?: () => void;
  settingsPanel?: ReactNode;
  systemNotes?: ReadonlyArray<{ id: string; text: string }>;
  errorText?: string | null;
  /** Extra control next to the error line (BYOK / retry). */
  errorAction?: ReactNode;
  disabled?: boolean;
  /**
   * When true and callbacks are provided, last-turn regen/edit chrome is shown.
   * Foundry/embed hosts that do not support mutation pass false.
   */
  allowTurnMutation?: boolean;
  onRegenerate?: () => void;
  /** Host truncates the thread and POSTs with X-Digi-Turn-Mode: edit_last_user. */
  onEditLastUser?: (text: string) => void;
};

const EMPTY_MESSAGES: UIMessage[] = [];

function CliMessage({
  role,
  uiMessage,
  isStreaming,
  isLastAssistant,
  isLastUser,
  editingLastUser,
  editDraft,
  onEditDraftChange,
  onSubmitEdit,
  onCancelEdit,
  allowTurnMutation,
  canRegenerate,
  canEditLastUser,
  canExportThread,
  onCopy,
  onExportThread,
  onBeginEdit,
  onRegenerate,
}: {
  role: string;
  uiMessage?: UIMessage;
  isStreaming?: boolean;
  isLastAssistant?: boolean;
  isLastUser?: boolean;
  editingLastUser?: boolean;
  editDraft?: string;
  onEditDraftChange?: (value: string) => void;
  onSubmitEdit?: () => void;
  onCancelEdit?: () => void;
  allowTurnMutation?: boolean;
  canRegenerate?: boolean;
  canEditLastUser?: boolean;
  canExportThread?: boolean;
  onCopy?: (message: UIMessage) => void;
  onExportThread?: () => void;
  onBeginEdit?: () => void;
  onRegenerate?: () => void;
}) {
  const isUser = role === "user";
  const showEditForm = Boolean(isLastUser && editingLastUser);
  return (
    <MessagePrimitive.Root
      className={cn("dc-term-row group/message", isUser ? "dc-term-row-user" : "dc-term-row-assistant")}
    >
      <span className="dc-term-marker" aria-hidden>
        {isUser ? ">" : "▸"}
      </span>
      <div className="dc-term-body">
        {showEditForm ? (
          <div className="flex flex-col gap-2">
            <textarea
              className="min-h-[4.5rem] w-full resize-y rounded-none border border-border/60 bg-transparent p-2 text-sm"
              value={editDraft}
              onChange={(e) => onEditDraftChange?.(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.preventDefault();
                  onCancelEdit?.();
                } else if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSubmitEdit?.();
                }
              }}
              aria-label="Edit last message"
              maxLength={2000}
            />
            <div className="flex flex-wrap items-center gap-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-[11px] text-muted-foreground"
                disabled={!editDraft?.trim()}
                onClick={onSubmitEdit}
              >
                save
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-[11px] text-muted-foreground"
                onClick={onCancelEdit}
              >
                cancel
              </Button>
            </div>
          </div>
        ) : uiMessage ? (
          <div className="space-y-3">
            <UiMessageParts message={uiMessage} isStreaming={isStreaming} />
            <LegacyActivityHydrate message={uiMessage} isStreaming={isStreaming} />
          </div>
        ) : (
          <MessagePrimitive.Parts components={cliMessagePartComponents} />
        )}
        {!showEditForm && uiMessage ? (
          <div
            className={cn(
              "mt-2 flex flex-wrap items-center gap-1 opacity-0 transition-opacity group-hover/message:opacity-100 group-focus-within/message:opacity-100",
              (isLastAssistant || isLastUser) && "opacity-100",
            )}
          >
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 text-[11px] text-muted-foreground"
              onClick={() => onCopy?.(uiMessage)}
            >
              copy
            </Button>
            {isLastAssistant && canExportThread ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-[11px] text-muted-foreground"
                onClick={onExportThread}
                aria-label="Download thread as markdown"
              >
                md
              </Button>
            ) : null}
            {allowTurnMutation && isLastAssistant && onRegenerate ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-[11px] text-muted-foreground"
                disabled={!canRegenerate}
                title="Replays the full digigraph workflow on this session"
                onClick={onRegenerate}
              >
                regen
              </Button>
            ) : null}
            {allowTurnMutation && isLastUser && onBeginEdit ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 text-[11px] text-muted-foreground"
                disabled={!canEditLastUser}
                title="Replaces this turn and replays the digigraph workflow"
                onClick={onBeginEdit}
              >
                edit
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </MessagePrimitive.Root>
  );
}

export function CliThread({
  emptyHint,
  headerSlot,
  footerSlot,
  belowViewportSlot,
  formReplacement,
  suggestions = [],
  placeholder = "ask digichat",
  ariaLabel = "digichat",
  className,
  layout = "page",
  slashVisibility,
  extraSlash = [],
  onSlashCommand,
  onSendRequest,
  onOpenSettings,
  onByok,
  onLanguageChange,
  onReset,
  settingsPanel,
  systemNotes = [],
  errorText,
  errorAction,
  disabled,
  allowTurnMutation = false,
  onRegenerate,
  onEditLastUser,
}: CliThreadProps) {
  const chat = useAISDKChat<UIMessage>();
  const [draft, setDraft] = useState("");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [notes, setNotes] = useState<string[]>([]);
  const [editingLastUser, setEditingLastUser] = useState(false);
  const [editDraft, setEditDraft] = useState("");

  const busy = chat?.status === "streaming" || chat?.status === "submitted";
  const ready = chat?.status === "ready" || chat?.status === undefined;
  const messages = chat?.messages ?? EMPTY_MESSAGES;

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  let lastUserIndex = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === "user") {
      lastUserIndex = i;
      break;
    }
  }
  const lastUser = lastUserIndex >= 0 ? messages[lastUserIndex] : undefined;
  const canRegenerate =
    allowTurnMutation && !busy && !!lastAssistant && messages.length > 0 && ready && !editingLastUser;
  const canEditLastUser = allowTurnMutation && !busy && !!lastUser && ready && !editingLastUser;
  const canExportThread = !busy && messages.some((m) => messagePlainText(m).trim());

  const slashMatches = matchingSlashCommands(draft, slashVisibility);
  const paletteRows = useMemo(() => {
    const q = draft.trim().toLowerCase();
    const extraMatches =
      q.startsWith("/") && !/\s/.test(q)
        ? extraSlash.filter((row) => row.cmd.startsWith(q) || q.startsWith(row.cmd))
        : [];
    return [
      ...slashMatches.map((c) => ({
        cmd: c.names[0],
        hint: c.hint,
        fill: c.needsArg ? `${c.names[0]} ` : c.names[0],
      })),
      ...extraMatches.map((row) => ({ cmd: row.cmd, hint: row.hint, fill: `${row.cmd} ` })),
    ];
  }, [draft, extraSlash, slashMatches]);

  const sendText = useCallback(
    (raw: string, forceTool?: string) => {
      const text = raw.trim();
      if (!text || !chat) return;
      if (onSendRequest?.(text, forceTool ? { forceTool } : undefined)) return;
      void chat.sendMessage({ text });
    },
    [chat, onSendRequest],
  );

  const handleSlash = useCallback(
    (raw: string): boolean => {
      const parsed = parseSlashInput(raw);
      if (parsed.kind === "none") return false;
      if (parsed.kind === "unknown") {
        if (onSlashCommand?.(raw)) return true;
        setNotes((n) => [...n, `Unknown command \`${parsed.name}\`. Type /help.`]);
        return true;
      }
      if (parsed.kind === "incomplete") {
        setDraft(parsed.prefix);
        return true;
      }
      const { command, arg } = parsed;
      if (command.forceTool) {
        sendText(arg, command.forceTool);
        return true;
      }
      if (command.id === "help") {
        setNotes((n) => [...n, slashHelpText(slashVisibility)]);
        return true;
      }
      if (command.id === "copy" || command.id === "export") {
        const settled =
          busy && messages.length > 0 && messages[messages.length - 1]?.role === "assistant"
            ? messages.slice(0, -1)
            : messages;
        const last = [...settled].reverse().find((m) => m.role === "assistant" && messagePlainText(m).trim());
        if (command.id === "copy") {
          if (!last) {
            setNotes((n) => [...n, "No assistant answer to copy yet."]);
            return true;
          }
          const sources = messageSourceCitations(last);
          const md = serializeAssistantMarkdown(messagePlainText(last), sources);
          void copyMarkdownWithFallback(md, { filename: "digichat-answer.md" });
          setNotes((n) => [...n, "Copied last answer."]);
          return true;
        }
        const turns = settled
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) =>
            m.role === "assistant"
              ? {
                  role: "assistant" as const,
                  content: messagePlainText(m),
                  sources: messageSourceCitations(m),
                }
              : { role: "user" as const, content: messagePlainText(m) },
          );
        const md = serializeThreadMarkdown(turns);
        if (!md.trim()) {
          setNotes((n) => [...n, "Nothing to export yet."]);
          return true;
        }
        try {
          downloadMarkdown("digichat-thread.md", md);
          setNotes((n) => [...n, "Exported thread as digichat-thread.md."]);
        } catch {
          setNotes((n) => [...n, "Export failed in this browser."]);
        }
        return true;
      }
      if (command.id === "new") {
        if (onReset) onReset();
        else chat?.setMessages([]);
        return true;
      }
      if (command.id === "byok") {
        (onByok ?? onOpenSettings)?.();
        return true;
      }
      if (command.id === "settings") {
        onOpenSettings?.();
        return true;
      }
      if (command.id === "lang" && onLanguageChange) {
        onLanguageChange(arg.toLowerCase());
        setNotes((n) => [...n, `Language set to ${arg.toLowerCase()}.`]);
        return true;
      }
      if (onSlashCommand?.(raw)) return true;
      return false;
    },
    [
      busy,
      chat,
      messages,
      onByok,
      onLanguageChange,
      onOpenSettings,
      onReset,
      onSlashCommand,
      sendText,
      slashVisibility,
    ],
  );

  const onCopy = useCallback(async (m: UIMessage) => {
    const plain = messagePlainText(m);
    const sources = m.role === "assistant" ? messageSourceCitations(m) : undefined;
    const markdown =
      m.role === "assistant" ? serializeAssistantMarkdown(plain, sources) : plain.trim();
    await copyMarkdownWithFallback(markdown, { filename: "digichat-answer.md" });
  }, []);

  const onExportThread = useCallback(() => {
    const turns = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => {
        const content = messagePlainText(m);
        if (m.role === "assistant") {
          return {
            role: "assistant" as const,
            content,
            sources: messageSourceCitations(m),
          };
        }
        return { role: "user" as const, content };
      });
    const md = serializeThreadMarkdown(turns);
    if (!md.trim()) return;
    downloadMarkdown("digichat-thread.md", md);
  }, [messages]);

  const beginEditLastUser = useCallback(() => {
    if (!canEditLastUser || !lastUser) return;
    setEditingLastUser(true);
    setEditDraft(messagePlainText(lastUser));
  }, [canEditLastUser, lastUser]);

  const cancelEditLastUser = useCallback(() => {
    setEditingLastUser(false);
    setEditDraft("");
  }, []);

  const submitEditLastUser = useCallback(() => {
    const next = editDraft.trim();
    if (!next || !onEditLastUser || busy) return;
    setEditingLastUser(false);
    setEditDraft("");
    onEditLastUser(next);
  }, [busy, editDraft, onEditLastUser]);

  const onComposerKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (paletteRows.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      setPaletteIndex((i) => nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, paletteRows.length));
      return;
    }
    if (paletteRows.length && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const row = paletteRows[paletteIndex] ?? paletteRows[0];
      if (!row) return;
      // Exact command already typed — run it instead of re-filling the draft.
      const typed = draft.trim();
      if (typed === row.cmd || typed === row.fill.trim()) {
        setDraft("");
        handleSlash(typed);
        return;
      }
      setDraft(row.fill);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const t = draft.trim();
      if (!t) return;
      setDraft("");
      if (t.startsWith("/")) {
        handleSlash(t);
        return;
      }
      sendText(t);
    }
  };

  return (
    <ThreadPrimitive.Root
      className={cn("flex h-full min-h-0 flex-1 flex-col", layout === "embed" && "dc-session dc-session-embed", className)}
      aria-label={ariaLabel}
    >
      {headerSlot}
      <ThreadPrimitive.Viewport className="relative min-h-0 flex-1 overflow-y-auto rounded-none border border-border/40 dc-term-pane dc-thread">
        <ThreadPrimitive.Empty>
          {emptyHint === null
            ? null
            : (emptyHint ?? (
                <div className="dc-term-row dc-term-row-assistant">
                  <span className="dc-term-marker">▸</span>
                  <div className="dc-term-body" style={{ color: "var(--text-secondary)" }}>
                    digichat ready. Ask a question or type <code className="font-mono">/help</code>.
                  </div>
                </div>
              ))}
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages>
          {({ message }) => {
            const ui = messages.find((m) => m.id === message.id);
            const isLastAssistant =
              !!ui && ui.role === "assistant" && ui.id === lastAssistant?.id;
            const isLastUser = !!ui && lastUserIndex >= 0 && ui.id === lastUser?.id;
            return (
              <CliMessage
                role={message.role}
                uiMessage={ui}
                isStreaming={busy && isLastAssistant}
                isLastAssistant={isLastAssistant}
                isLastUser={isLastUser}
                editingLastUser={editingLastUser}
                editDraft={editDraft}
                onEditDraftChange={setEditDraft}
                onSubmitEdit={submitEditLastUser}
                onCancelEdit={cancelEditLastUser}
                allowTurnMutation={allowTurnMutation}
                canRegenerate={canRegenerate}
                canEditLastUser={canEditLastUser}
                canExportThread={canExportThread}
                onCopy={onCopy}
                onExportThread={onExportThread}
                onBeginEdit={onEditLastUser ? beginEditLastUser : undefined}
                onRegenerate={onRegenerate}
              />
            );
          }}
        </ThreadPrimitive.Messages>
        {systemNotes.map((n) => (
          <div key={n.id} className="dc-term-row dc-term-row-assistant">
            <span className="dc-term-marker" aria-hidden>
              ·
            </span>
            <div className="dc-term-body" style={{ color: "var(--text-secondary)", fontFamily: "var(--font-family-mono)", fontSize: 12 }}>
              {n.text}
            </div>
          </div>
        ))}
        {notes.map((text, i) => (
          <div key={`n-${i}`} className="dc-term-row dc-term-row-assistant">
            <span className="dc-term-marker" aria-hidden>
              ·
            </span>
            <pre className="dc-term-body font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
              {text}
            </pre>
          </div>
        ))}
        {errorText ? (
          <div className="dc-term-row dc-term-row-assistant">
            <span className="dc-term-marker" style={{ color: "var(--down)" }}>
              ✗
            </span>
            <div className="dc-term-body" style={{ color: "var(--down)" }}>
              {errorText}
              {errorAction ? <> {errorAction}</> : null}
            </div>
          </div>
        ) : null}
        {settingsPanel}
        {suggestions.length && messages.length === 0 ? (
          <div className="dc-suggestions">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                className="dc-chip"
                disabled={busy || disabled}
                onClick={() => sendText(s)}
              >
                {s}
              </button>
            ))}
          </div>
        ) : null}
      </ThreadPrimitive.Viewport>

      {belowViewportSlot}

      {formReplacement ?? (
        <>
          {paletteRows.length ? (
            <ul className="dc-slash mb-1 list-none border-b border-border/40 px-2 py-1" role="listbox" aria-label="Slash commands">
              {paletteRows.map((row, i) => (
                <li key={`${row.cmd}-${row.hint}`}>
                  <button
                    type="button"
                    role="option"
                    className={cn("flex w-full gap-3 px-1 py-1 text-left text-xs", i === paletteIndex && "text-[var(--accent)]")}
                    aria-selected={i === paletteIndex}
                    onMouseEnter={() => setPaletteIndex(i)}
                    onClick={() => setDraft(row.fill)}
                  >
                    <span className="font-mono min-w-[5.5rem]">{row.cmd}</span>
                    <span className="opacity-70">{row.hint}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <ComposerPrimitive.Root className="app-input">
            <span className={cn("app-input-marker", draft.trimStart().startsWith("/") && "dc-input-slash-glyph")}>
              {draft.trimStart().startsWith("/") ? "/" : ">"}
            </span>
            <ComposerPrimitive.Input
              placeholder={placeholder}
              className="app-input-field"
              rows={1}
              disabled={busy || disabled}
              submitMode="none"
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                setPaletteIndex(0);
              }}
              onKeyDown={onComposerKey}
            />
            {busy ? (
              <button
                type="button"
                className="slash-hint"
                onClick={() => void chat?.stop()}
              >
                stop
              </button>
            ) : (
              <span className="slash-hint" aria-hidden>
                <kbd>↵</kbd>
              </span>
            )}
          </ComposerPrimitive.Root>
        </>
      )}
      {footerSlot}
    </ThreadPrimitive.Root>
  );
}
