"use client";

import { Thread } from "@/app/(baseline)/stock/thread.aui";
import { BotIcon } from "lucide-react";
import { AssistantModal } from "./assistant-modal";
import { useDocsConfig } from "./config-provider";
import type { DocsPage } from "./types";

export function DocsAssistant({
  currentPage,
  mode,
  defaultOpen = false,
}: {
  currentPage: DocsPage;
  onSelectPage: (pageId: string) => void;
  mode: "sidebar" | "modal";
  defaultOpen?: boolean;
}) {
  const { assistant } = useDocsConfig();
  const thread = (
    <Thread
      components={{
        Welcome: () => (
          <div className="mb-4 px-4 text-center">
            <h2 className="text-lg font-medium">{assistant.welcome.headline}</h2>
            {assistant.welcome.body ? (
              <p className="mt-1 text-sm text-muted-foreground">{assistant.welcome.body}</p>
            ) : null}
          </div>
        ),
      }}
    />
  );

  if (mode === "sidebar") {
    return (
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
    );
  }

  return (
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
  );
}
