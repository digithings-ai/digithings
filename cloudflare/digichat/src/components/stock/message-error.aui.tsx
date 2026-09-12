"use client";

import {
  ActionBarPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  useAuiState,
} from "@assistant-ui/react";
import type { FC } from "react";
import { parseEmbedChatError, formatEmbedChatError } from "@/lib/embed-chat-error";

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

/** assistant-ui error banner: short copy plus optional API-detail disclosure. */
export const MessageError: FC = () => {
  const raw = useAuiState((s) => messageStatusErrorText(s.message.status ?? {}));
  const parsed = parseEmbedChatError(raw ? new Error(raw) : undefined);
  const title =
    formatEmbedChatError(raw ? new Error(raw) : undefined) ??
    parsed?.message ??
    (raw && raw.trim() ? raw : "The request failed.");
  const detail = parsed?.detail;
  const code = parsed?.code;

  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 rounded-md border border-hair bg-surface p-3 text-sm text-ink">
        <div className="min-w-0 flex-1">
          <ErrorPrimitive.Message className="aui-message-error-message whitespace-pre-wrap">
            {title}
          </ErrorPrimitive.Message>
          {detail || code ? (
            <details className="mt-2 text-xs opacity-90">
              <summary className="cursor-pointer select-none">API details</summary>
              {code ? <p className="mt-1 font-mono">code: {code}</p> : null}
              {detail ? (
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono">
                  {detail}
                </pre>
              ) : null}
            </details>
          ) : null}
        </div>
        {/* #3910: the errored turn must offer retry where the copy shows. */}
        <ActionBarPrimitive.Reload asChild>
          <button
            type="button"
            className="aui-message-error-retry mt-2 inline-flex shrink-0 items-center self-start rounded-md border border-hair bg-surface px-2.5 py-1 text-xs font-medium text-ink transition-colors hover:bg-muted"
          >
            Retry
          </button>
        </ActionBarPrimitive.Reload>
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};
