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
import { supportAssistantConfig } from "@/lib/support/assistant-config";
import { supportToolData } from "@/lib/support/tool-data";
import {
  chooseScenario,
  type AttachmentMeta,
  type IssueAnalysis,
  type SupportSummary,
} from "@/lib/support/mock-tools";
import type { SupportToolId } from "@/lib/support/types";

export const maxDuration = 30;

const demoTiming = {
  beforeFirstTextMs: 250,
  beforeToolInputMs: 220,
  toolThinkingMs: 480,
  afterToolOutputMs: 350,
  wordMs: 14,
};

const SYSTEM_PROMPT = [
  `You are ${supportAssistantConfig.assistantName}, ${supportAssistantConfig.agentPrompt.persona} for ${supportAssistantConfig.productName}.`,
  supportAssistantConfig.agentPrompt.instructions,
  supportAssistantConfig.agentPrompt.responseStyle,
  "Mention uploaded screenshots or logs when present.",
].join("\n");

export async function POST(req: Request) {
  const {
    messages,
    system,
    tools,
  }: {
    messages: UIMessage[];
    system?: string;
    tools?: Record<string, { description?: string; parameters: JSONSchema7 }>;
  } = await req.json();

  const uiStream = createUIMessageStream({
    execute: async ({ writer }) => {
      if (!process.env.OPENAI_API_KEY) {
        await streamSupportFallback(writer, messages);
        return;
      }
      await streamProviderRun(writer, messages, tools ?? {}, system);
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
  system?: string,
) {
  const aiSDKTools = {
    ...frontendTools(tools),
  };

  const result = streamText({
    model: openai(process.env.OPENAI_MODEL ?? "gpt-5.4-nano"),
    system: system ?? SYSTEM_PROMPT,
    messages: await convertToModelMessages(messages, { tools: aiSDKTools }),
    stopWhen: stepCountIs(6),
    tools: aiSDKTools,
  });

  for await (const chunk of result.toUIMessageStream()) {
    writer.write(chunk);
  }
}

async function streamSupportFallback(writer: UIMessageStreamWriter, messages: UIMessage[]) {
  const lastUserMessage = messages.filter((message) => message.role === "user").at(-1);
  const description = extractText(lastUserMessage) || "My integration stopped syncing.";
  const scenarioId = chooseScenario(description, supportToolData);
  const scenario =
    supportToolData.scenarioPacks.find((pack) => pack.id === scenarioId) ??
    supportToolData.scenarioPacks[0];
  const flow = supportAssistantConfig.demoFlows[scenarioId];
  const attachments = extractAttachments(lastUserMessage);
  const effectiveAttachments =
    attachments.length > 0
      ? attachments
      : scenario.mockAttachments.map((name) => ({ name, type: "mock" }));

  const messageId = `msg-${crypto.randomUUID()}`;
  writer.write({ type: "start", messageId });
  writer.write({ type: "start-step" });
  await sleep(demoTiming.beforeFirstTextMs);

  let analysis: IssueAnalysis | undefined;
  let summary: SupportSummary | undefined;

  for (const step of flow.steps) {
    await writeText(writer, step.assistantText);

    if (step.toolId === "analyzeIssue") {
      const input = {
        ...(step.input as Record<string, unknown>),
        description,
        attachments: effectiveAttachments,
        scenarioId,
      };
      const output = {
        ...(step.output as Record<string, unknown>),
        attachments: effectiveAttachments,
      };
      analysis = await writeToolCall(writer, step.toolId, input, async () => output as IssueAnalysis);
      continue;
    }

    if (step.toolId === "createSupportSummary") {
      const stepInput = step.input as { issue?: IssueAnalysis };
      const issue = analysis ?? stepInput.issue;
      if (!issue) {
        await writeToolCall(
          writer,
          step.toolId,
          step.input as Record<string, unknown>,
          async () => step.output,
        );
        continue;
      }
      const input = {
        ...(step.input as Record<string, unknown>),
        issue,
        attachments: effectiveAttachments,
        scenarioId,
      };
      const output = {
        ...(step.output as Record<string, unknown>),
        summary: `${issue.affectedService}: ${issue.likelyCause}`,
        attachments: effectiveAttachments.map((attachment) => attachment.name),
      };
      summary = await writeToolCall(writer, step.toolId, input, async () => output as SupportSummary);
      continue;
    }

    await writeToolCall(
      writer,
      step.toolId,
      step.input as Record<string, unknown>,
      async () => step.output,
    );
  }

  await writeText(
    writer,
    `Diagnosis: ${analysis?.likelyCause ?? "Support issue analyzed."}

Handoff: ${summary?.ticketId ?? "SUP-DEMO"} is ready for ${summary?.recommendedOwner ?? "Support"} as ${summary?.priority ?? "P3"}.
Next step: ${summary?.nextResponseSla ?? "Review the support summary."}

${flow.finalResponse}

${supportAssistantConfig.demoModeNotice}`,
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
  toolName: SupportToolId,
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

function extractText(message: UIMessage | undefined) {
  return (
    message?.parts
      ?.flatMap((part) => (part.type === "text" ? [part.text] : []))
      .join(" ")
      .trim() ?? ""
  );
}

function extractAttachments(message: UIMessage | undefined): AttachmentMeta[] {
  return (
    message?.parts?.flatMap((part) => {
      if (part.type === "text") return [];
      const record = part as Record<string, unknown>;
      return [
        {
          name:
            String(record.filename ?? record.name ?? record.mediaType ?? part.type) || "attachment",
          type: String(record.mediaType ?? record.mimeType ?? part.type),
        },
      ];
    }) ?? []
  );
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
