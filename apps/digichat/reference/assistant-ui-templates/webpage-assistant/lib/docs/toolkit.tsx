"use client";

import { docsAssistantConfig } from "@/lib/docs/assistant-config";
import { buildDocsToolParameters } from "@/lib/docs/tool-parameters";
import { renderDocsTool } from "@/lib/docs/tool-ui";
import type { DocsAssistantConfig } from "@/lib/docs/types";
import type { Toolkit } from "@assistant-ui/react";

export function createDocsToolkit({
  assistant = docsAssistantConfig,
  previewRef = {},
  onSelectPage,
}: {
  assistant?: DocsAssistantConfig;
  previewRef?: {
    previewToken?: string | null;
    previewSessionId?: string | null;
    previewVersion?: string | null;
  };
  onSelectPage?: (pageId: string) => void;
} = {}) {
  return Object.fromEntries(
    assistant.tools.map((tool) => [
      tool.id,
      {
        description: tool.aiDescription,
        parameters: buildDocsToolParameters(tool.id),
        execute: async (args: unknown, { abortSignal }: { abortSignal?: AbortSignal }) => {
          const response = await fetch(`/api/docs/tools/${tool.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ args, ...previewRef }),
            signal: abortSignal,
          });
          if (!response.ok) {
            throw new Error(`Tool ${tool.id} failed`);
          }
          return response.json();
        },
        render: renderDocsTool({ tool, onSelectPage }),
      },
    ]),
  ) satisfies Toolkit;
}

export const docsToolkit = createDocsToolkit();
