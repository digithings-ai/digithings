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
    "border-destructive/20 bg-destructive/[0.04] text-foreground [&_.aui-chat-notice-title]:text-destructive",
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

/**
 * The full detail (error text, traceback, JSON payload). Never cut and never
 * folded: it sits in a max-height scroll area (Chris, 21 Oct).
 */
export const ChatNoticeDetail: FC<{ text: string }> = ({ text }) => (
  <pre
    data-slot="chat-notice-detail"
    className="aui-chat-notice-detail mt-1 max-h-72 overflow-auto overscroll-contain whitespace-pre-wrap break-words font-mono text-[0.68rem] leading-relaxed"
  >
    {text}
  </pre>
);

/** Marker + title + optional detail + optional action, inside a notice root. */
export const ChatNoticeContent: FC<{
  tone: ChatNoticeTone;
  title: ReactNode;
  detail?: string;
  extra?: ReactNode;
  action?: ReactNode;
}> = ({ tone, title, detail, extra, action }) => (
  <>
    <DotMatrix
      state={tone === "error" ? "error" : "idle"}
      label={tone === "error" ? "Error" : "Status"}
      className={cn(
        "aui-chat-notice-marker !size-3 mt-0.5 shrink-0",
        tone === "error" ? "text-destructive/60" : "text-muted-foreground",
      )}
    />
    <div className="min-w-0 flex-1">
      <div
        data-slot="chat-notice-title"
        className="aui-chat-notice-title whitespace-pre-wrap break-words font-medium"
      >
        {title}
      </div>
      {detail ? <ChatNoticeDetail text={detail} /> : null}
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
    <ChatNoticeContent tone="status" title={message} detail={detail} />
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
