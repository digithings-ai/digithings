"use client";

import {
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

export const MessageError: FC = () => {
  const raw = useAuiState((s) => messageStatusErrorText(s.message.status ?? {}));
  const { title, detail, code } = splitError(raw);

  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:bg-red-500/15 dark:text-red-300">
        <DotMatrix state="error" label="Error" />
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
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};
