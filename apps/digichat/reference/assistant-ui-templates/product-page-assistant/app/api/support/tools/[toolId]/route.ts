import {
  analyzeIssue,
  createSupportSummary,
  type AttachmentMeta,
  type IssueAnalysis,
} from "@/lib/support/mock-tools";
import { supportAssistantConfig } from "@/lib/support/assistant-config";
import { supportToolData } from "@/lib/support/tool-data";
import type { BuiltInSupportToolId, SupportScenarioId } from "@/lib/support/types";

type ToolHandler = (args: any, signal?: AbortSignal) => Promise<unknown>;

const handlers = {
  analyzeIssue: (args: {
    description: string;
    attachments?: AttachmentMeta[];
    service?: string;
    scenarioId?: SupportScenarioId;
  }) => analyzeIssue({ ...args, toolData: supportToolData }),
  createSupportSummary: (args: {
    issue: IssueAnalysis;
    attachments?: AttachmentMeta[];
    scenarioId?: SupportScenarioId;
  }) => createSupportSummary({ ...args, toolData: supportToolData }),
} satisfies Record<BuiltInSupportToolId, ToolHandler>;

export async function POST(req: Request, { params }: { params: Promise<{ toolId: string }> }) {
  const { toolId } = await params;
  const body = await req.json();
  const tool = supportAssistantConfig.tools.find((item) => item.id === toolId);

  if (!tool) {
    return new Response("Unknown support tool", { status: 404 });
  }

  const handler = handlers[tool.id as BuiltInSupportToolId];
  if (!handler) {
    return Response.json(
      tool.mockResponse ?? {
        toolId,
        input: body.args ?? body,
        note: "Mock response for a configured custom tool.",
      },
    );
  }

  // Real implementation: replace the mock handler with the integration described
  // by tool.realImplementationHint.
  const result = await handler(body.args ?? body);
  return Response.json(result);
}
