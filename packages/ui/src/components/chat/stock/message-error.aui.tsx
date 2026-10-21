"use client";

import {
  ActionBarPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  useAuiState,
} from "@assistant-ui/react";
import type { FC } from "react";
import { ChatNoticeContent, ChatNoticeDetail, chatNoticeRootProps } from "./chat-notice";
import { Button } from "@digithings/ui/ui";
import { useSkinRuntime, type SkinErrorParsers } from "./skin-runtime";

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
export const MessageError: FC<Partial<SkinErrorParsers>> = ({
  parseError,
  formatError,
}) => {
  const runtime = useSkinRuntime();
  // Hosts provide the product parsers via SkinRuntimeProvider (errorParsers).
  // Without one the banner falls back to the raw message text (WS4).
  const parse = parseError ?? runtime.errorParsers?.parseError ?? (() => null);
  const format =
    formatError ?? runtime.errorParsers?.formatError ?? (() => null);
  const raw = useAuiState((s) => messageStatusErrorText(s.message.status ?? {}));
  const parsed = parse(raw ? new Error(raw) : undefined);
  const title =
    format(raw ? new Error(raw) : undefined) ??
    parsed?.message ??
    (raw && raw.trim() ? raw : "The request failed.");
  const detail = parsed?.detail;
  const code = parsed?.code;

  const rawDetail = raw && raw.trim() !== title ? raw : undefined;

  // DIG-4459: the boxed, red-tinted notice shared with tool errors and status
  // lines, on assistant-ui's ErrorPrimitive.Root.
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root {...chatNoticeRootProps("error", "aui-message-error-root mt-2")}>
        <ChatNoticeContent
          tone="error"
          title={
            <ErrorPrimitive.Message className="aui-message-error-message whitespace-pre-wrap">
              {title}
            </ErrorPrimitive.Message>
          }
          detail={detail}
          extra={
            <>
              {code || (rawDetail && !detail) ? (
                <div className="aui-message-error-details mt-1 text-muted-foreground">
                {code ? <p className="mt-1 font-mono">code: {code}</p> : null}
                {rawDetail && !detail ? <ChatNoticeDetail text={rawDetail} /> : null}
              </div>
              ) : null}
              {/* #3910: the errored turn must offer retry where the copy shows. */}
              <ActionBarPrimitive.Reload asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="aui-message-error-retry mt-2 shrink-0 items-center self-start border-destructive/25 bg-transparent text-destructive hover:bg-destructive/10"
                >
                  Retry
                </Button>
              </ActionBarPrimitive.Reload>
            </>
          }
        />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
};
