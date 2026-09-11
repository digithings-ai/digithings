"use client";

import {
  CodeSnippetToolCard,
  GenericToolCard,
  PagePreviewToolCard,
  SourceResultsToolCard,
} from "@/components/docs/tool-cards";
import type { DocsAssistantConfig, DocsToolRenderer } from "@/lib/docs/types";
import type React from "react";

type ToolRenderFunction = (props: any) => React.ReactNode;

export const supportedDocsToolRenderers = {
  sourceResults: (props) => <SourceResultsToolCard {...props} />,
  pagePreview: (props) => <PagePreviewToolCard {...props} />,
  codeSnippet: (props) => <CodeSnippetToolCard {...props} />,
  generic: (props) => <GenericToolCard {...props} />,
} satisfies Record<DocsToolRenderer, ToolRenderFunction>;

export function renderDocsTool({
  tool,
  onSelectPage,
}: {
  tool: DocsAssistantConfig["tools"][number];
  onSelectPage?: (pageId: string) => void;
}) {
  const renderer =
    supportedDocsToolRenderers[tool.rendererType] ?? supportedDocsToolRenderers.generic;

  return (props: any) =>
    renderer({
      ...props,
      toolName: tool.id,
      displayName: tool.displayName,
      expectedRenderer: tool.rendererType,
      onSelectPage,
    });
}
