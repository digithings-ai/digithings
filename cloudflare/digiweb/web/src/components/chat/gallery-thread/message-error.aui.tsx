"use client";

import {
  ActionBarPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
} from "@assistant-ui/react";
import { CircleAlertIcon, RefreshCwIcon } from "lucide-react";

/**
 * Error state — the assistant-ui error-state element pattern: a quiet banner
 * where the reply would have been, naming the failure with a retry path.
 *
 * MessagePrimitive.Error renders the banner only while the message carries an
 * error (status incomplete + reason error), so nothing here has to check.
 * ActionBarPrimitive.Reload re-runs the failed turn.
 */
export function MessageError() {
  return (
    <MessagePrimitive.Error>
      <ErrorPrimitive.Root className="aui-message-error-root mt-2 flex items-start gap-2.5 rounded-2xl bg-destructive/5 px-4 py-3 text-sm dark:bg-destructive/10">
        <CircleAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive/80" />
        <ErrorPrimitive.Message className="aui-message-error-message min-w-0 flex-1 whitespace-pre-wrap text-destructive" />
        <ActionBarPrimitive.Reload className="aui-message-error-retry ms-auto flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium text-destructive transition-colors hover:bg-destructive/10">
          <RefreshCwIcon className="size-3" />
          Retry
        </ActionBarPrimitive.Reload>
      </ErrorPrimitive.Root>
    </MessagePrimitive.Error>
  );
}
