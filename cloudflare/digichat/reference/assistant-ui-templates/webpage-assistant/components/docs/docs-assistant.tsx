"use client";

import { AssistantModal } from "@/components/assistant-ui/assistant-modal";
import { Thread } from "@/components/assistant-ui/thread";
import { useDocsConfig } from "@/lib/docs/config-provider";
import { createDocsToolkit } from "@/lib/docs/toolkit";
import type { DocsPage } from "@/lib/docs/types";
import { AssistantRuntimeProvider, Suggestions, Tools, useAui } from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/react-ai-sdk";
import { lastAssistantMessageIsCompleteWithToolCalls } from "ai";
import { BotIcon } from "lucide-react";
import { useMemo } from "react";

export function DocsAssistant({
  currentPage,
  onSelectPage,
  mode,
  defaultOpen = false,
}: {
  currentPage: DocsPage;
  onSelectPage: (pageId: string) => void;
  mode: "sidebar" | "modal";
  defaultOpen?: boolean;
}) {
  const { assistant } = useDocsConfig();
  const searchParams =
    typeof window === "undefined" ? null : new URLSearchParams(window.location.search);
  const previewToken = searchParams?.get("p") ?? null;
  const previewSessionId = searchParams?.get("s") ?? null;
  const previewVersion = searchParams?.get("v") ?? null;
  const previewRef = useMemo(
    () => ({ previewToken, previewSessionId, previewVersion }),
    [previewToken, previewSessionId, previewVersion],
  );

  const runtime = useChatRuntime({
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls,
    transport: new AssistantChatTransport({
      api: "/api/chat",
      body: {
        ...previewRef,
        currentPage: {
          id: currentPage.id,
          title: currentPage.title,
          url: currentPage.url,
          description: currentPage.description,
        },
      },
    }),
  });

  const aui = useAui({
    tools: Tools({
      toolkit: createDocsToolkit({
        assistant,
        previewRef,
        onSelectPage,
      }),
    }),
    suggestions: Suggestions(
      assistant.suggestedPrompts.map((prompt) => ({
        ...prompt,
        label: prompt.title,
        prompt: prompt.prompt ?? prompt.title,
      })),
    ),
  });

  const thread = (
    <Thread
      welcomeHeadline={assistant.welcome.headline}
      welcomeBody={assistant.welcome.body}
      composerPlaceholder={assistant.labels.composerPlaceholder}
    />
  );

  return (
    <AssistantRuntimeProvider aui={aui} runtime={runtime}>
      {mode === "sidebar" ? (
        <div className="flex h-full flex-col">
          <div className="border-b px-4 py-3">
            <div className="flex items-center gap-2">
              <div className="flex size-8 items-center justify-center rounded-md bg-[var(--docs-accent-soft)] text-[var(--docs-accent)]">
                <BotIcon className="size-4" />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold">{assistant.assistantName}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {assistant.labels.currentPage}: {currentPage.title}
                </div>
              </div>
            </div>
          </div>
          <div className="min-h-0 flex-1">{thread}</div>
        </div>
      ) : (
        <AssistantModal
          defaultOpen={defaultOpen}
          tooltipClosed={assistant.assistantName}
          tooltipOpen="Close assistant"
        >
          <div className="flex h-full flex-col">
            <div className="border-b px-4 py-3">
              <div className="text-sm font-semibold">{assistant.assistantName}</div>
              <div className="truncate text-xs text-muted-foreground">
                {assistant.labels.currentPage}: {currentPage.title}
              </div>
            </div>
            <div className="min-h-0 flex-1">{thread}</div>
          </div>
        </AssistantModal>
      )}
    </AssistantRuntimeProvider>
  );
}
