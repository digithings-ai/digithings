import { openai } from "@ai-sdk/openai";
import { frontendTools } from "@assistant-ui/react-ai-sdk";
import {
  convertToModelMessages,
  createUIMessageStream,
  JsonToSseTransformStream,
  stepCountIs,
  streamText,
  type JSONSchema7,
  type UIMessage,
  type UIMessageStreamWriter,
} from "ai";
import { docsAssistantConfig } from "@/lib/docs/assistant-config";
import { defaultDocsHostUi } from "@/lib/docs/host-ui";
import {
  chooseDemoFlow,
  getPageById,
} from "@/lib/docs/mock-tools";
import type { DemoFlowStep, DocsPage, DocsToolId } from "@/lib/docs/types";

export const maxDuration = 30;

type CurrentPageContext = Pick<DocsPage, "id" | "title" | "url" | "description">;

const demoTiming = {
  beforeFirstTextMs: 250,
  beforeToolInputMs: 180,
  toolThinkingMs: 360,
  afterToolOutputMs: 300,
  wordMs: 14,
};

const buildSystemPrompt = (currentPage?: CurrentPageContext) =>
  [
    `You are ${docsAssistantConfig.assistantName} for ${docsAssistantConfig.productName}.`,
    "Answer as a concise product documentation assistant.",
    "Use docs tools for searches, page metadata, and code snippets when relevant.",
    "openPage returns metadata only. UI navigation is handled separately by the preview page action.",
    currentPage
      ? `Current page context: ${currentPage.title} (${currentPage.url}) - ${currentPage.description}`
      : "",
  ]
    .filter(Boolean)
    .join("\n");

export async function POST(req: Request) {
  const {
    messages,
    system,
    tools,
    currentPage,
  }: {
    messages: UIMessage[];
    system?: string;
    tools?: Record<string, { description?: string; parameters: JSONSchema7 }>;
    currentPage?: CurrentPageContext;
  } = await req.json();

  const uiStream = createUIMessageStream({
    execute: async ({ writer }) => {
      if (!process.env.OPENAI_API_KEY) {
        await streamDocsFallback(writer, messages, currentPage);
        return;
      }
      await streamProviderRun(writer, messages, tools ?? {}, system, currentPage);
    },
  });

  return new Response(
    uiStream.pipeThrough(new JsonToSseTransformStream()).pipeThrough(new TextEncoderStream()),
    {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    },
  );
}

async function streamProviderRun(
  writer: UIMessageStreamWriter,
  messages: UIMessage[],
  tools: Record<string, { description?: string; parameters: JSONSchema7 }>,
  system: string | undefined,
  currentPage?: CurrentPageContext,
) {
  const aiSDKTools = {
    ...frontendTools(tools),
  };

  const result = streamText({
    model: openai(process.env.OPENAI_MODEL ?? "gpt-5.4-nano"),
    system: system ?? buildSystemPrompt(currentPage),
    messages: await convertToModelMessages(messages, { tools: aiSDKTools }),
    stopWhen: stepCountIs(6),
    tools: aiSDKTools,
  });

  for await (const chunk of result.toUIMessageStream()) {
    writer.write(chunk);
  }
}

async function streamDocsFallback(
  writer: UIMessageStreamWriter,
  messages: UIMessage[],
  currentPageContext?: CurrentPageContext,
) {
  const lastUserMessage = messages.filter((message) => message.role === "user").at(-1);
  const prompt = extractText(lastUserMessage) || "Debug a 401 response";
  const flowId = chooseDemoFlow({
    message: prompt,
    assistant: docsAssistantConfig,
  });
  const currentPage = getPageById(
    currentPageContext?.id,
    defaultDocsHostUi.root.props.pages,
    defaultDocsHostUi.root.props.defaultPageId,
  );

  const messageId = `msg-${crypto.randomUUID()}`;
  writer.write({ type: "start", messageId });
  writer.write({ type: "start-step" });
  await sleep(demoTiming.beforeFirstTextMs);

  if (flowId === "currentPage") {
    await writeText(
      writer,
      `You are on ${currentPage.title}. ${currentPage.description} Recommended next pages: ${currentPage.relatedPageIds.join(", ")}.`,
    );
    writer.write({ type: "finish-step" });
    writer.write({ type: "finish" });
    return;
  }

  const flow = docsAssistantConfig.demoFlows[flowId];
  await writeText(
    writer,
    `${docsAssistantConfig.productName}: ${flow.title}.\n\nCurrent page context: ${currentPage.title} - ${currentPage.description}\n\n`,
  );

  for (const step of flow.steps) {
    await writeText(writer, `${step.assistantText}\n\n`);
    await writeToolStep(writer, step);
  }

  await writeText(
    writer,
    `\n${flow.finalResponse}\n\n${docsAssistantConfig.demoModeNotice}`,
  );
  writer.write({ type: "finish-step" });
  writer.write({ type: "finish" });
}

async function writeText(writer: UIMessageStreamWriter, text: string) {
  const textId = `txt-${crypto.randomUUID()}`;
  writer.write({ type: "text-start", id: textId });
  for (const word of text.match(/\S+\s*|\s+/g) ?? [text]) {
    writer.write({ type: "text-delta", id: textId, delta: word });
    await sleep(demoTiming.wordMs);
  }
  writer.write({ type: "text-end", id: textId });
}

async function writeToolCall<T>(
  writer: UIMessageStreamWriter,
  toolName: DocsToolId,
  input: Record<string, unknown>,
  execute: () => Promise<T>,
) {
  const toolCallId = `call-${crypto.randomUUID()}`;
  await sleep(demoTiming.beforeToolInputMs);
  writer.write({
    type: "tool-input-available",
    toolCallId,
    toolName,
    input,
    providerExecuted: true,
  });
  await sleep(demoTiming.toolThinkingMs);
  const output = await execute();
  writer.write({
    type: "tool-output-available",
    toolCallId,
    output,
    providerExecuted: true,
  });
  await sleep(demoTiming.afterToolOutputMs);
  return output;
}

async function writeToolStep(writer: UIMessageStreamWriter, step: DemoFlowStep) {
  return writeToolCall(writer, step.toolId, step.input as Record<string, unknown>, async () => step.output);
}

function extractText(message: UIMessage | undefined) {
  return (
    message?.parts
      ?.flatMap((part) => (part.type === "text" ? [part.text] : []))
      .join(" ")
      .trim() ?? ""
  );
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
