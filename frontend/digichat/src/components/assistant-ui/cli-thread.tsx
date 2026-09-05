"use client";

/**
 * CLI-skinned assistant-ui thread + composer.
 * Uses existing .dc-* / .app-input session tokens — not stock ChatGPT chrome.
 */
import { useCallback, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import { useAISDKChat } from "@assistant-ui/ai-sdk";
import {
  ActionBarPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import type { UIMessage } from "ai";
import { ChatActivities, matchingSlashCommands, nextPaletteIndex, parseSlashInput, slashHelpText, citationHits, serializeAssistantMarkdown, serializeThreadMarkdown, copyMarkdownWithFallback, downloadMarkdown, type SlashVisibility } from "@digithings/digichat-ui";
import { ChatMarkdown } from "@digithings/web";
import { messageActivities } from "@/lib/chat-activity";
import { cn } from "@/lib/utils";

export type CliThreadProps = {
  emptyHint?: ReactNode;
  headerSlot?: ReactNode;
  footerSlot?: ReactNode;
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
  onLanguageChange?: (code: string) => void;
  /** Called for /new instead of only clearing the client transcript. */
  onReset?: () => void;
  settingsPanel?: ReactNode;
  systemNotes?: ReadonlyArray<{ id: string; text: string }>;
  errorText?: string | null;
  /** Extra control next to the error line (BYOK / retry). */
  errorAction?: ReactNode;
  disabled?: boolean;
};

const EMPTY_MESSAGES: UIMessage[] = [];

function messagePlainText(message: UIMessage): string {
  return (message.parts ?? [])
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("");
}

function CliMessage({
  role,
  uiMessage,
  isStreaming,
}: {
  role: string;
  uiMessage?: UIMessage;
  isStreaming?: boolean;
}) {
  const isUser = role === "user";
  const activities = uiMessage ? messageActivities(uiMessage, { settle: !isStreaming }) : [];
  const text = uiMessage ? messagePlainText(uiMessage) : "";
  return (
    <MessagePrimitive.Root
      className={cn("dc-term-row group/message", isUser ? "dc-term-row-user" : "dc-term-row-assistant")}
    >
      <span className="dc-term-marker" aria-hidden>
        {isUser ? ">" : "▸"}
      </span>
      <div className="dc-term-body">
        {!isUser && activities.length ? <ChatActivities activities={activities} /> : null}
        {text ? (
          <ChatMarkdown
            source={text}
            className={cn("text-[var(--text-primary)]", isStreaming && "dc-term-streaming")}
          />
        ) : (
          <MessagePrimitive.Parts />
        )}
        {!isUser ? (
          <ActionBarPrimitive.Root className="mt-2 flex flex-wrap items-center gap-1 opacity-0 transition-opacity group-hover/message:opacity-100">
            <ActionBarPrimitive.Copy className="h-6 text-[11px] text-muted-foreground">
              copy
            </ActionBarPrimitive.Copy>
          </ActionBarPrimitive.Root>
        ) : null}
      </div>
    </MessagePrimitive.Root>
  );
}

export function CliThread({
  emptyHint,
  headerSlot,
  footerSlot,
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
  onLanguageChange,
  onReset,
  settingsPanel,
  systemNotes = [],
  errorText,
  errorAction,
  disabled,
}: CliThreadProps) {
  const chat = useAISDKChat<UIMessage>();
  const [draft, setDraft] = useState("");
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [notes, setNotes] = useState<string[]>([]);

  const busy = chat?.status === "streaming" || chat?.status === "submitted";
  const messages = chat?.messages ?? EMPTY_MESSAGES;

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
          const sources = citationHits(messageActivities(last)).map((h) => ({ title: h.title, path: h.path }));
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
                  sources: citationHits(messageActivities(m)).map((h) => ({ title: h.title, path: h.path })),
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
      if (command.id === "settings" || command.id === "byok") {
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
    [busy, chat, messages, onLanguageChange, onOpenSettings, onReset, onSlashCommand, sendText, slashVisibility],
  );

  const onComposerKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (paletteRows.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      setPaletteIndex((i) => nextPaletteIndex(i, e.key === "ArrowDown" ? 1 : -1, paletteRows.length));
      return;
    }
    if (paletteRows.length && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const row = paletteRows[paletteIndex] ?? paletteRows[0];
      if (row) setDraft(row.fill);
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
            const isLast =
              !!ui && ui.role === "assistant" && ui.id === messages[messages.length - 1]?.id;
            return (
              <CliMessage
                role={message.role}
                uiMessage={ui}
                isStreaming={busy && isLast}
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
