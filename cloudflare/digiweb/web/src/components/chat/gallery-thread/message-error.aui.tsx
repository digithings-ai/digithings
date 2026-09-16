"use client";

import {
  ActionBarPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  useAuiState,
} from "@assistant-ui/react";
import type { FC } from "react";
import { DotMatrix } from "../DotMatrix";

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
    const title = parsed.message || (typeof code === "string" ? code : raw);
    return {
      title,
      detail: parsed.detail,
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

  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 flex items-start gap-2.5 rounded-2xl bg-destructive/5 px-4 py-3 text-sm dark:bg-destructive/10">
        <DotMatrix
          state="error"
          label="Error"
          className="mt-0.5 size-4 shrink-0 text-destructive/80"
        />
        <div className="min-w-0 flex-1">
          <ErrorPrimitive.Message className="aui-message-error-message whitespace-pre-wrap text-destructive">
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
        <ActionBarPrimitive.Reload className="aui-message-error-retry ms-auto flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10 disabled:pointer-events-none disabled:opacity-50">
          Retry
        </ActionBarPrimitive.Reload>
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};
