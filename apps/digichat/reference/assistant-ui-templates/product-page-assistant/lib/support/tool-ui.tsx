"use client";

import {
  GenericToolCard,
  IssueAnalysisToolCard,
  SupportSummaryToolCard,
} from "@/components/support/tool-cards";
import type { SupportAssistantConfig, SupportToolRenderer } from "@/lib/support/types";
import type React from "react";

type ToolRenderFunction = (props: any) => React.ReactNode;

export const supportedToolRenderers = {
  analysis: (props) => <IssueAnalysisToolCard {...props} />,
  summary: (props) => <SupportSummaryToolCard {...props} />,
  generic: (props) => <GenericToolCard {...props} />,
} satisfies Record<SupportToolRenderer, ToolRenderFunction>;

export function renderSupportTool(tool: SupportAssistantConfig["tools"][number]) {
  const renderer = supportedToolRenderers[tool.rendererType] ?? supportedToolRenderers.generic;

  return (props: any) =>
    renderer({
      ...props,
      toolName: tool.id,
      displayName: tool.displayName,
      expectedRendererType: tool.rendererType,
    });
}
