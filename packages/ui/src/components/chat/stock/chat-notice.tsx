"use client";

import type { FC, ReactNode } from "react";
import { DotMatrix } from "../DotMatrix";
import { cn } from "@/lib/utils";

/**
 * One boxed notice for everything the backend tells the reader outside the
 * answer itself (DIG-4459 chat transparency): a failed turn, a failed tool
 * call, a status line. Error notices are red-tinted, status notices are
 * neutral. The message error banner puts these props on assistant-ui's
 * ErrorPrimitive.Root; tool errors and status lines use a plain div.
 */
export type ChatNoticeTone = "error" | "status";

const TONE_CLASS: Record<ChatNoticeTone, string> = {
  error:
    "border-destructive/40 bg-destructive/10 text-foreground [&_.aui-chat-notice-title]:text-destructive",
  status: "border-border bg-muted/40 text-foreground",
};

export function chatNoticeRootProps(
  tone: ChatNoticeTone,
  className?: string,
): {
  className: string;
  "data-slot": "chat-notice";
  "data-tone": ChatNoticeTone;
  role: "alert" | "status";
} {
  return {
    className: cn(
      "aui-chat-notice flex w-full items-start gap-2 rounded-md border px-3 py-2 text-xs leading-snug",
      TONE_CLASS[tone],
      className,
    ),
    "data-slot": "chat-notice",
    "data-tone": tone,
    role: tone === "error" ? "alert" : "status",
  };
}

/** Lines or characters past which the detail folds behind a toggle. */
const LONG_DETAIL_LINES = 8;
const LONG_DETAIL_CHARS = 600;

export function isLongDetail(text: string): boolean {
  return (
    text.length > LONG_DETAIL_CHARS || text.split("\n").length > LONG_DETAIL_LINES
  );
}

/**
 * The full detail (error text, traceback, JSON payload). Never cut: a long
 * one folds behind "Show full error" and scrolls when open; a short one shows
 * inline.
 */
export const ChatNoticeDetail: FC<{ text: string; label?: string }> = ({
  text,
  label = "Show full error",
}) => {
  const body = (
    <pre
      data-slot="chat-notice-detail"
      className="aui-chat-notice-detail mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-words font-mono text-[0.68rem] leading-relaxed"
    >
      {text}
    </pre>
  );
  if (!isLongDetail(text)) return body;
  return (
    <details data-slot="chat-notice-disclosure" className="aui-chat-notice-disclosure mt-1">
      <summary className="cursor-pointer select-none text-muted-foreground">
        {label} ({text.split("\n").length} lines)
      </summary>
      {body}
    </details>
  );
};

/** Marker + title + optional detail + optional action, inside a notice root. */
export const ChatNoticeContent: FC<{
  tone: ChatNoticeTone;
  title: ReactNode;
  detail?: string;
  detailLabel?: string;
  extra?: ReactNode;
  action?: ReactNode;
}> = ({ tone, title, detail, detailLabel, extra, action }) => (
  <>
    <DotMatrix
      state={tone === "error" ? "error" : "idle"}
      label={tone === "error" ? "Error" : "Status"}
      className={cn(
        "aui-chat-notice-marker !size-3 mt-0.5 shrink-0",
        tone === "error" ? "text-destructive/80" : "text-muted-foreground",
      )}
    />
    <div className="min-w-0 flex-1">
      <div
        data-slot="chat-notice-title"
        className="aui-chat-notice-title whitespace-pre-wrap break-words font-medium"
      >
        {title}
      </div>
      {detail ? <ChatNoticeDetail text={detail} label={detailLabel} /> : null}
      {extra}
    </div>
    {action}
  </>
);

/** A neutral status line from the backend ("Waiting for model capacity…"). */
export const ChatStatusNotice: FC<{
  message: string;
  detail?: string;
  className?: string;
}> = ({ message, detail, className }) => (
  <div {...chatNoticeRootProps("status", cn("my-1", className))}>
    <ChatNoticeContent tone="status" title={message} detail={detail} detailLabel="Show details" />
  </div>
);

/**
 * A backend notice carried as a data part: `data-notice` with
 * `{ message, detail?, tone? }`, or a `data-status` that carries a `message`.
 * Returns null for every other data part (connection state, conversation id,
 * usage…), which have their own renderers or none.
 */
export function backendNoticeOf(part: {
  readonly type: string;
  readonly name?: string;
  readonly data?: unknown;
}): { tone: ChatNoticeTone; message: string; detail?: string } | null {
  if (part.type !== "data") return null;
  if (part.name !== "notice" && part.name !== "status") return null;
  const data = (part.data ?? {}) as { message?: unknown; detail?: unknown; tone?: unknown };
  const message = typeof data.message === "string" ? data.message.trim() : "";
  if (!message) return null;
  const detail = typeof data.detail === "string" && data.detail.trim() ? data.detail : undefined;
  const tone: ChatNoticeTone = data.tone === "error" ? "error" : "status";
  return { tone, message, ...(detail ? { detail } : {}) };
}

/** Renders a backend notice part, or nothing. */
export const BackendNotice: FC<{
  part: { readonly type: string; readonly name?: string; readonly data?: unknown };
}> = ({ part }) => {
  const notice = backendNoticeOf(part);
  if (!notice) return null;
  if (notice.tone === "status") {
    return <ChatStatusNotice message={notice.message} detail={notice.detail} />;
  }
  return (
    <div {...chatNoticeRootProps("error", "my-1")}>
      <ChatNoticeContent tone="error" title={notice.message} detail={notice.detail} />
    </div>
  );
};
