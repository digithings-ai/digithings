"use client";

/**
 * DigichatThread — first-party assistant-ui Thread for digichat.
 *
 * Capability from primitives (copy / edit / regenerate / branch / attachments /
 * markdown / tools / reasoning). Look from digiweb tokens + ChatMessage /
 * ChatMarkdown / ChatThinking / ChatToolCall. User and assistant both left;
 * role is `>` / `▸` / `·`. Do not import ink.
 */
import {
  ActionBarPrimitive,
  AuiIf,
  AttachmentPrimitive,
  BranchPickerPrimitive,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePartPrimitive,
  MessagePrimitive,
  SuggestionPrimitive,
  ThreadPrimitive,
  useAuiState,
} from "@assistant-ui/react";
import {
  useEffect,
  useId,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { ChatMarkdown } from "./ChatMarkdown";
import { ChatMessage } from "./ChatMessage";
import { ChatStreamCursor } from "./ChatStreamCursor";
import { ChatThinking } from "./ChatThinking";
import { ChatToolCall, type ChatToolCallStatus } from "./ChatToolCall";
import { DIGICHAT_GLYPHS, digichatSurfaces } from "./chat-surfaces";

export type DigichatThreadProps = {
  welcome?: string;
  placeholder?: string;
  className?: string;
  /** Embed send-gate / system page-context attach. Form onSubmit. */
  onComposerSubmit?: (event: FormEvent<HTMLFormElement>) => void;
};

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function resultLines(result: unknown): string | undefined {
  if (result == null) return undefined;
  if (typeof result === "string") return result;
  try {
    return JSON.stringify(result, null, 2);
  } catch {
    return String(result);
  }
}

function toolStatus(part: {
  isError?: boolean;
  result?: unknown;
}): ChatToolCallStatus {
  if (part.isError) return "error";
  if (part.result !== undefined) return "ok";
  return "running";
}

export function DigichatThread({
  welcome = "What should we inspect?",
  placeholder = "Ask digichat…",
  className,
  onComposerSubmit,
}: DigichatThreadProps) {
  return (
    <ThreadPrimitive.Root
      className={cx(digichatSurfaces.thread, className)}
      data-user-align="left"
      style={{ ["--thread-max-width" as string]: "44rem" }}
    >
      <ThreadPrimitive.Viewport className={digichatSurfaces.viewport}>
        <AuiIf condition={(s) => s.thread.isEmpty}>
          <Welcome headline={welcome} />
        </AuiIf>

        <ThreadPrimitive.Messages>
          {({ message }) => {
            if (message.role === "system") return <SystemMessage />;
            if (message.composer.isEditing) return <EditComposer />;
            if (message.role === "user") return <UserMessage />;
            return <AssistantMessage />;
          }}
        </ThreadPrimitive.Messages>

        <ThreadPrimitive.ViewportFooter className={digichatSurfaces.footer}>
          <ThreadPrimitive.ScrollToBottom className={digichatSurfaces.scrollBtn}>
            ↓ scroll
          </ThreadPrimitive.ScrollToBottom>
          <Composer placeholder={placeholder} onSubmit={onComposerSubmit} />
        </ThreadPrimitive.ViewportFooter>
      </ThreadPrimitive.Viewport>
    </ThreadPrimitive.Root>
  );
}

function Welcome({ headline }: { headline: string }) {
  return (
    <div className={digichatSurfaces.welcome}>
      <p className={digichatSurfaces.welcomeKicker}>{"// digichat"}</p>
      <p className={digichatSurfaces.welcomeTitle}>{headline}</p>
      <div className={digichatSurfaces.suggestions}>
        <ThreadPrimitive.Suggestions>
          {() => (
            <SuggestionPrimitive.Trigger send className={digichatSurfaces.chip}>
              <SuggestionPrimitive.Title />
            </SuggestionPrimitive.Trigger>
          )}
        </ThreadPrimitive.Suggestions>
      </div>
    </div>
  );
}

function SystemMessage() {
  return (
    <MessagePrimitive.Root data-role="system" className={digichatSurfaces.turn}>
      <ChatMessage role="system">
        <MessagePrimitive.Parts>
          {({ part }) =>
            part.type === "text" ? (
              <span className="whitespace-pre-wrap">{part.text}</span>
            ) : null
          }
        </MessagePrimitive.Parts>
      </ChatMessage>
    </MessagePrimitive.Root>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root data-role="user" className={digichatSurfaces.turn}>
      <ChatMessage role="user">
        <MessagePrimitive.Parts>
          {({ part }) => {
            if (part.type === "text") {
              return <span className="whitespace-pre-wrap">{part.text}</span>;
            }
            if (part.type === "image") {
              return <MessagePartPrimitive.Image className="max-w-full" />;
            }
            return null;
          }}
        </MessagePrimitive.Parts>
      </ChatMessage>
      <MessagePrimitive.Attachments>
        {() => (
          <div className="ml-[1.8rem]">
            <DigichatAttachmentChip removable={false} />
          </div>
        )}
      </MessagePrimitive.Attachments>
      <ActionBarPrimitive.Root
        hideWhenRunning
        autohide="not-last"
        className={digichatSurfaces.actionRow}
      >
        <ActionBarPrimitive.Edit className={digichatSurfaces.action}>
          edit
        </ActionBarPrimitive.Edit>
      </ActionBarPrimitive.Root>
    </MessagePrimitive.Root>
  );
}

function EditComposer() {
  return (
    <MessagePrimitive.Root data-role="user" className={digichatSurfaces.turn}>
      <ChatMessage role="user">
        <ComposerPrimitive.Root className={digichatSurfaces.composer}>
          <ComposerPrimitive.Input className={digichatSurfaces.composerInput} />
          <div className="flex justify-end gap-[0.55rem]">
            <ComposerPrimitive.Cancel className={digichatSurfaces.stop}>
              cancel
            </ComposerPrimitive.Cancel>
            <ComposerPrimitive.Send className={digichatSurfaces.send}>
              save
            </ComposerPrimitive.Send>
          </div>
        </ComposerPrimitive.Root>
      </ChatMessage>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root data-role="assistant" className={digichatSurfaces.turn}>
      <ChatMessage role="assistant">
        <div className="flex min-w-0 flex-col gap-[0.55rem]">
          <MessagePrimitive.Parts>
            {({ part }) => <AssistantPart part={part} />}
          </MessagePrimitive.Parts>
          <MessagePrimitive.Error>
            <ErrorPrimitive.Root className={digichatSurfaces.error} role="alert">
              <ErrorPrimitive.Message />
              <ActionBarPrimitive.Reload className={cx(digichatSurfaces.action, "ml-[0.75rem]")}>
                retry
              </ActionBarPrimitive.Reload>
            </ErrorPrimitive.Root>
          </MessagePrimitive.Error>
        </div>
      </ChatMessage>
      <div className={digichatSurfaces.actionRow}>
        <BranchPickerPrimitive.Root
          hideWhenSingleBranch
          data-slot="aui_branch-picker"
          className="inline-flex items-center gap-[0.35rem] font-mono text-[0.66rem] text-ink-mute"
        >
          <BranchPickerPrimitive.Previous className={digichatSurfaces.action}>
            ‹
          </BranchPickerPrimitive.Previous>
          <span>
            <BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
          </span>
          <BranchPickerPrimitive.Next className={digichatSurfaces.action}>
            ›
          </BranchPickerPrimitive.Next>
        </BranchPickerPrimitive.Root>
        <ActionBarPrimitive.Root hideWhenRunning autohide="not-last">
          <ActionBarPrimitive.Copy className={digichatSurfaces.action}>
            copy
          </ActionBarPrimitive.Copy>
          <ActionBarPrimitive.Reload className={digichatSurfaces.action}>
            regenerate
          </ActionBarPrimitive.Reload>
          <ActionBarPrimitive.ExportMarkdown className={digichatSurfaces.action}>
            export
          </ActionBarPrimitive.ExportMarkdown>
        </ActionBarPrimitive.Root>
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantPart({ part }: { part: { type: string } & Record<string, unknown> }) {
  switch (part.type) {
    case "text":
      return (
        <ChatMarkdown source={String(part.text ?? "")}>
          <MessagePartPrimitive.InProgress>
            <ChatStreamCursor />
          </MessagePartPrimitive.InProgress>
        </ChatMarkdown>
      );
    case "reasoning": {
      const text = String(part.text ?? "");
      const steps = text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean);
      return (
        <div data-slot="aui_reasoning">
          <ChatThinking
            label={steps.length ? "Thought" : "Thinking…"}
            steps={steps.length ? steps : undefined}
            count={null}
          >
            {steps.length ? null : (
              <pre className="m-0 whitespace-pre-wrap font-mono text-[0.78rem] text-term-mute">
                {text}
              </pre>
            )}
          </ChatThinking>
        </div>
      );
    }
    case "tool-call": {
      const toolUI = part.toolUI as ReactNode | undefined;
      if (toolUI) return toolUI;
      const name = String(part.toolName ?? "tool");
      const args = String(part.argsText ?? "");
      const status = toolStatus({
        isError: Boolean(part.isError),
        result: part.result,
      });
      const output = resultLines(part.result);
      return (
        <div data-slot="aui_tool-fallback">
          <ChatToolCall
            name={name}
            args={args || undefined}
            status={status}
            defaultOpen={status !== "running"}
            lines={output ? [output] : undefined}
          />
        </div>
      );
    }
    case "source":
      return part.sourceType === "url" && typeof part.url === "string" ? (
        <a
          href={part.url}
          className="font-mono text-[0.74rem] text-accent underline-offset-2 hover:underline"
          data-source
        >
          {typeof part.title === "string" ? part.title : part.url}
        </a>
      ) : (
        <span className="font-mono text-[0.74rem] text-term-mute">
          {String(part.title ?? "")}
        </span>
      );
    case "image":
      return <MessagePartPrimitive.Image className="max-w-full" />;
    case "file": {
      const filename = typeof part.filename === "string" ? part.filename : "file";
      const href =
        typeof part.data === "string"
          ? part.data
          : typeof part.url === "string"
            ? part.url
            : undefined;
      return href ? (
        <a href={href} download={filename} className="font-mono text-[0.74rem] text-accent">
          {filename}
        </a>
      ) : (
        <span className="font-mono text-[0.74rem] text-term-mute">{filename}</span>
      );
    }
    case "generative-ui":
      return null;
    default:
      return null;
  }
}

function Composer({
  placeholder,
  onSubmit,
}: {
  placeholder: string;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <ComposerPrimitive.Root className={digichatSurfaces.composer} onSubmit={onSubmit}>
      <ComposerPrimitive.AttachmentDropzone className="contents">
        <ComposerPrimitive.Attachments>
          {() => <DigichatAttachmentChip removable />}
        </ComposerPrimitive.Attachments>
        <div className={digichatSurfaces.composerRow}>
          <span className={digichatSurfaces.composerGlyph} aria-hidden="true">
            {DIGICHAT_GLYPHS.user}
          </span>
          <ComposerPrimitive.Input
            placeholder={placeholder}
            rows={1}
            className={digichatSurfaces.composerInput}
            aria-label="Message"
          />
        </div>
        <div className={digichatSurfaces.composerTray}>
          <div className="flex min-w-0 items-center gap-[0.65rem]">
            <ComposerPrimitive.AddAttachment
              data-slot="aui_composer-add-attachment"
              className={digichatSurfaces.action}
            >
              attach
            </ComposerPrimitive.AddAttachment>
            <AuiIf condition={(s) => s.composer.dictation != null}>
              <ComposerPrimitive.Dictate className={digichatSurfaces.action}>
                dictate
              </ComposerPrimitive.Dictate>
            </AuiIf>
          </div>
          <div className="flex items-center gap-[0.45rem]">
            <AuiIf condition={(s) => s.thread.isRunning}>
              <ComposerPrimitive.Cancel className={digichatSurfaces.stop}>
                stop
              </ComposerPrimitive.Cancel>
            </AuiIf>
            <AuiIf condition={(s) => !s.thread.isRunning}>
              <ComposerPrimitive.Send className={digichatSurfaces.send}>
                send
              </ComposerPrimitive.Send>
            </AuiIf>
          </div>
        </div>
      </ComposerPrimitive.AttachmentDropzone>
    </ComposerPrimitive.Root>
  );
}

function attachmentTypeLabel(type: string): string {
  switch (type) {
    case "image":
      return "image";
    case "document":
      return "document";
    case "file":
      return "file";
    default:
      return type;
  }
}

function decodeDataUrlLocal(url: string): string {
  if (!url.startsWith("data:")) return url;
  const comma = url.indexOf(",");
  if (comma < 0) return "";
  const header = url.slice(5, comma);
  const payload = url.slice(comma + 1);
  if (header.includes(";base64")) {
    try {
      const binary = atob(payload);
      const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
      return new TextDecoder().decode(bytes);
    } catch {
      return payload;
    }
  }
  try {
    return decodeURIComponent(payload);
  } catch {
    return payload;
  }
}

function DigichatAttachmentChip({ removable }: { removable: boolean }) {
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const name = useAuiState((s) => s.attachment.name);
  const type = useAuiState((s) => s.attachment.type);
  const content = useAuiState((s) => s.attachment.content);
  const typeLabel = attachmentTypeLabel(type);
  const filePart = content?.find((part) => part.type === "file");
  const textPart = content?.find((part) => part.type === "text");
  const raw =
    filePart && "data" in filePart && typeof filePart.data === "string"
      ? filePart.data
      : textPart && "text" in textPart && typeof textPart.text === "string"
        ? textPart.text
        : "";
  const mime =
    filePart && "mimeType" in filePart && typeof filePart.mimeType === "string"
      ? filePart.mimeType
      : "";
  const body = raw.startsWith("data:") ? decodeDataUrlLocal(raw) : raw;
  const html =
    mime.includes("html") ||
    raw.startsWith("data:text/html") ||
    name.toLowerCase().endsWith(".html");

  return (
    <>
      <AttachmentPrimitive.Root className="aui-attachment-root relative">
        <div className="aui-attachment-chip">
          <button
            type="button"
            className="aui-attachment-chip-hit min-w-0"
            aria-label={`${typeLabel} attachment ${name}`}
            data-digichat-attach-chip={name}
            onClick={() => setOpen(true)}
          >
            <span className="aui-attachment-chip-body inline-flex min-w-0 items-center gap-1.5">
              <span className="aui-attachment-chip-name min-w-0 truncate">
                <AttachmentPrimitive.Name />
              </span>
              <span className="aui-attachment-chip-type shrink-0">{typeLabel}</span>
            </span>
          </button>
          {removable ? (
            <AttachmentPrimitive.Remove className="aui-attachment-chip-remove">
              ×
            </AttachmentPrimitive.Remove>
          ) : null}
        </div>
      </AttachmentPrimitive.Root>
      {open
        ? createPortal(
            <AttachmentViewer
              titleId={titleId}
              name={name}
              body={body}
              html={html}
              onClose={() => setOpen(false)}
            />,
            document.body,
          )
        : null}
    </>
  );
}

function AttachmentViewer({
  titleId,
  name,
  body,
  html,
  onClose,
}: {
  titleId: string;
  name: string;
  body: string;
  html: boolean;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="digichat-attach-viewer"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      data-digichat-attach-viewer={name}
      onClick={onClose}
    >
      <div
        className="digichat-attach-viewer__panel"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="digichat-attach-viewer__head">
          <h2 id={titleId} className="digichat-attach-viewer__title">
            {name}
          </h2>
          <button
            type="button"
            className="digichat-attach-viewer__close"
            onClick={onClose}
          >
            close
          </button>
        </header>
        {html ? (
          <iframe
            className="digichat-attach-viewer__frame"
            sandbox=""
            srcDoc={body}
            title={name}
          />
        ) : (
          <pre className="digichat-attach-viewer__pre">{body}</pre>
        )}
      </div>
    </div>
  );
}
