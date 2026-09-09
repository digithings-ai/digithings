"use client";

import { supportAssistantConfig } from "@/lib/support/assistant-config";
import { buildSupportToolParameters } from "@/lib/support/tool-parameters";
import { renderSupportTool } from "@/lib/support/tool-ui";
import type { SupportAssistantConfig } from "@/lib/support/types";
import type { Toolkit } from "@assistant-ui/react";

export function createSupportToolkit(
  assistant: SupportAssistantConfig = supportAssistantConfig,
  previewRef: {
    previewToken?: string | null;
    previewSessionId?: string | null;
    previewVersion?: string | null;
  } = {},
) {
  return Object.fromEntries(
    assistant.tools.map((tool) => [
      tool.id,
      {
        description: tool.aiDescription,
        parameters: buildSupportToolParameters(tool.id),
        execute: async (args: unknown, { abortSignal }: { abortSignal?: AbortSignal }) => {
          const res = await fetch(`/api/support/tools/${tool.id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ args, ...previewRef }),
            signal: abortSignal,
          });
          if (!res.ok) {
            throw new Error(`Tool ${tool.id} failed`);
          }
          return res.json();
        },
        render: renderSupportTool(tool),
      },
    ]),
  ) satisfies Toolkit;
}

export const supportToolkit = createSupportToolkit();
