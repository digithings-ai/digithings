"use client";

import {
  ActionBarPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  useAuiState,
} from "@assistant-ui/react";
import type { FC } from "react";
import { ChatNoticeContent, ChatNoticeDetail, chatNoticeRootProps } from "../stock/chat-notice";

function messageStatusErrorText(status: {
  type?: string;
  reason?: string;
  error?: unknown;
}): string | undefined {
  if (status.type !== "incomplete" || status.reason !== "error") return undefined;
  const error = status.error;
  if (typeof error === "string") return error;
  if (
    error &&
    typeof error === "object" &&
    "message" in error &&
    typeof (error as { message: unknown }).message === "string"
  ) {
    return (error as { message: string }).message;
  }
  return error != null ? String(error) : undefined;
}

function splitError(raw: string | undefined): {
  title: string;
  detail?: string;
  code?: string;
} {
  if (!raw?.trim()) return { title: "The request failed." };
  try {
    const parsed = JSON.parse(raw) as {
      error?: string;
      code?: string;
      message?: string;
      detail?: string;
    };
    const code = parsed.error ?? parsed.code;
    const title =
      (typeof parsed.message === "string" && parsed.message) ||
      (typeof code === "string" ? code : raw);
    return {
      title,
      detail: typeof parsed.detail === "string" ? parsed.detail : undefined,
      code: typeof code === "string" ? code : undefined,
    };
  } catch {
    return { title: raw };
  }
}

/**
 * Error state — the assistant-ui error-state element pattern: a quiet banner
 * where the reply would have been, naming the failure with a retry path.
 *
 * MessagePrimitive.Error renders the banner only while the message carries an
 * error (status incomplete + reason error), so nothing here has to check.
 * ActionBarPrimitive.Reload re-runs the failed turn.
 */
export const MessageError: FC = () => {
  const raw = useAuiState((s) => messageStatusErrorText(s.message.status ?? {}));
  const { title, detail, code } = splitError(raw);

  // DIG-4459: the backend's own words, whole, in the boxed error notice the
  // tool errors and status lines share. The headline is the parsed message;
  // the detail (or the raw payload when it says more) sits under it.
  const rawDetail = raw && raw.trim() !== title ? raw : undefined;

  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root
        {...chatNoticeRootProps("error", "aui-message-error-root mt-2")}
      >
        <ChatNoticeContent
          tone="error"
          title={
            <ErrorPrimitive.Message className="aui-message-error-message whitespace-pre-wrap">
              {title}
            </ErrorPrimitive.Message>
          }
          detail={detail}
          extra={
            code || (rawDetail && !detail) ? (
              <div className="aui-message-error-details mt-1 text-muted-foreground">
                {code ? <p className="mt-1 font-mono">code: {code}</p> : null}
                {rawDetail && !detail ? <ChatNoticeDetail text={rawDetail} /> : null}
              </div>
            ) : null
          }
          action={
            <ActionBarPrimitive.Reload className="aui-message-error-retry ms-auto flex shrink-0 items-center gap-1.5 rounded-full border border-destructive/25 px-3 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:pointer-events-none disabled:opacity-50">
              Retry
            </ActionBarPrimitive.Reload>
          }
        />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};
