import {
  generateCodeSnippet,
  openPage,
  searchDocs,
} from "@/lib/docs/mock-tools";
import { docsAssistantConfig } from "@/lib/docs/assistant-config";
import { defaultDocsHostUi } from "@/lib/docs/host-ui";
import type { BuiltInDocsToolId, DocsPage } from "@/lib/docs/types";

type ToolHandler = (
  args: any,
  signal: AbortSignal | undefined,
  pages: DocsPage[],
  defaultPageId: string,
) => Promise<unknown>;

const handlers = {
  searchDocs: (args: { query: string; limit?: number }, signal, pages) =>
    searchDocs({ ...args, pages }, signal),
  openPage: (args: { pageId: string }, signal, pages, defaultPageId) =>
    openPage({ ...args, pages, defaultPageId }, signal),
  generateCodeSnippet: (
    args: { topic: string; language?: "curl" | "typescript" | "python" },
    signal,
  ) => generateCodeSnippet(args, signal),
} satisfies Record<
  BuiltInDocsToolId,
  (
    args: any,
    signal: AbortSignal | undefined,
    pages: DocsPage[],
    defaultPageId: string,
  ) => Promise<unknown>
>;

export async function POST(
  req: Request,
  { params }: { params: Promise<{ toolId: string }> },
) {
  const { toolId } = await params;
  const body = await req.json();
  const tool = docsAssistantConfig.tools.find((item) => item.id === toolId);

  if (!tool) {
    return new Response("Unknown docs tool", { status: 404 });
  }

  const handler: ToolHandler | undefined = handlers[tool.id as BuiltInDocsToolId];
  if (!handler) {
    return Response.json(
      tool.mockResponse ?? {
        toolId,
        input: body.args ?? body,
        note: "Mock response for a configured custom tool.",
      },
    );
  }

  const result = await handler(
    body.args ?? body,
    req.signal,
    defaultDocsHostUi.root.props.pages,
    defaultDocsHostUi.root.props.defaultPageId,
  );
  return Response.json(result);
}
