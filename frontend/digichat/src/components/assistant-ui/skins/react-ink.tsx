"use client";

import { cn } from "@/lib/utils";
import {
  AuiIf,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import { MarkdownText } from "@/app/(vanilla)/stock/markdown-text";
import { useComposerCopy } from "@/components/stock/skin-chrome";

/**
 * Web facsimile of the official React Ink Terminal Assistant.
 * The TTY original (`ink` / `@assistant-ui/react-ink`) lives in
 * `reference/assistant-ui-templates/react-ink` and `frontend/digichat/cli`.
 * Next.js must not import those packages.
 */
export function ReactInkWeb() {
  const { title, welcome, placeholder } = useComposerCopy(
    'Working in this project. fetchUser() is flaky in prod and has no retry logic.',
    "Type a message... (Enter to send)",
  );
  return (
    <ThreadPrimitive.Root className="flex h-full flex-col bg-zinc-950 p-4 font-mono text-[13px] leading-5 text-zinc-100">
      <div className="mb-2 shrink-0">
        <span className="font-bold text-cyan-400">{title || "demo-agent"}</span>
        <span className="text-zinc-500">{"  ~/acme-app"}</span>
      </div>
      <div className="mb-3 shrink-0 text-zinc-500">model: demo · terminal</div>

      <AuiIf condition={(s) => s.thread.isEmpty}>
        <div className="mb-3 text-zinc-200">
          {welcome}
        </div>
      </AuiIf>

      <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto">
        <ThreadPrimitive.Messages>
          {({ message }) =>
            message.role === "user" ? <InkUserMessage /> : <InkAssistantMessage />
          }
        </ThreadPrimitive.Messages>
      </ThreadPrimitive.Viewport>

      <div className="mt-3 shrink-0 rounded border border-zinc-600 px-2 py-1">
        <div className="flex items-start gap-1">
          <span className="text-zinc-500">{"> "}</span>
          <ComposerPrimitive.Root className="flex min-w-0 flex-1 items-start gap-1">
            <ComposerPrimitive.Input
              placeholder={placeholder}
              className={cn(
                "w-full bg-transparent text-zinc-100 outline-none placeholder:text-zinc-600",
              )}
            />
            <ComposerPrimitive.Send className="sr-only">
              send
            </ComposerPrimitive.Send>
          </ComposerPrimitive.Root>
        </div>
      </div>
    </ThreadPrimitive.Root>
  );
}

function InkUserMessage() {
  return (
    <MessagePrimitive.Root className="mb-3">
      <span className="font-bold text-green-400">You: </span>
      <MessagePrimitive.Parts>
        {({ part }) =>
          part.type === "text" ? (
            <span className="whitespace-pre-wrap">{part.text}</span>
          ) : null
        }
      </MessagePrimitive.Parts>
    </MessagePrimitive.Root>
  );
}

function InkAssistantMessage() {
  return (
    <MessagePrimitive.Root className="mb-3">
      <div className="font-bold text-blue-400">AI:</div>
      <MessagePrimitive.Parts>
        {({ part }) => (part.type === "text" ? <MarkdownText /> : null)}
      </MessagePrimitive.Parts>
      <ErrorPrimitive.Root className="mt-1 text-red-400">
        <ErrorPrimitive.Message />
      </ErrorPrimitive.Root>
    </MessagePrimitive.Root>
  );
}
