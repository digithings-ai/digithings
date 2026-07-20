/**
 * Foundry backend adapter: calls Azure AI Foundry directly via
 * @azure/ai-projects (DefaultAzureCredential — the digichat container's own
 * managed identity, no relay hop, no stored key). Conversation state lives
 * in Foundry; the client echoes the conversation id back each turn using the
 * same generic contract external-relay-stream.ts already established
 * (data-externalConversation / X-External-Conversation).
 *
 * Supersedes the standalone datatap-digichat-relay Azure Function (digithings#1396):
 * that Function's source was never in this repo, so its two known bugs
 * (duplicated answers, duplicated "Searching…" trace) are fixed here from the
 * start rather than ported — see mapFoundryEvent below.
 */
import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import { createUIMessageStream, createUIMessageStreamResponse, type UIMessage } from "ai";
import { lastUserMessageText } from "./external-relay-stream";

export interface FoundryStreamEvent {
  type: string;
  [key: string]: unknown;
}

export interface OpenAIResponsesClientLike {
  conversations: {
    create(): Promise<{ id: string }>;
  };
  responses: {
    create(
      params: { conversation: string; input: string; stream: true },
      options: { signal?: AbortSignal; body: { agent_reference: { name: string; type: "agent_reference" } } }
    ): Promise<AsyncIterable<FoundryStreamEvent>>;
  };
}

export function defaultOpenAIClientFactory(projectEndpoint: string): OpenAIResponsesClientLike {
  const project = new AIProjectClient(projectEndpoint, new DefaultAzureCredential());
  return project.getOpenAIClient() as unknown as OpenAIResponsesClientLike;
}

type FoundryServerEvent =
  | { type: "text-delta"; delta: string }
  | { type: "trace"; label: string; status: "in_progress" | "completed" }
  | { type: "done" }
  | { type: "error"; message: string };

const FILE_SEARCH_LABEL = "Searching knowledge base…";

interface OutputItemDoneEvent extends FoundryStreamEvent {
  item?: {
    type?: string;
    queries?: string[];
    content?: Array<{
      annotations?: Array<{ type?: string; filename?: string; url?: string; title?: string }>;
    }>;
  };
}

function extractTextDelta(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return null;

  const record = value as Record<string, unknown>;
  if (typeof record.text === "string") return record.text;
  if (typeof record.delta === "string") return record.delta;

  if (Array.isArray(record.content)) {
    const fromContent = record.content
      .map((entry) => (entry && typeof entry === "object" ? (entry as Record<string, unknown>).text : null))
      .filter((text): text is string => typeof text === "string")
      .join("");
    if (fromContent) return fromContent;
  }

  return null;
}

function mapOutputItemDone(event: OutputItemDoneEvent): FoundryServerEvent | null {
  const item = event.item;
  if (item?.type === "file_search_call") {
    const queries = item.queries ?? [];
    const label =
      queries.length > 0 ? `Searched for: ${queries.map((q) => `"${q}"`).join(", ")}` : FILE_SEARCH_LABEL;
    return { type: "trace", label, status: "completed" };
  }
  if (item?.type === "message") {
    // Two citation shapes share this event: Foundry's native file_search tool annotates
    // with `filename`, while the azure_ai_search tool (Microsoft docs, "Connect an Azure
    // AI Search index to Foundry agents") emits `{type: "url_citation", url, title}`
    // instead — no filename at all. Handle both so sources show up regardless of which
    // grounding tool an agent uses.
    const sources = [
      ...new Set(
        (item.content ?? []).flatMap((c) =>
          (c.annotations ?? [])
            .map((a) => (a.type === "url_citation" ? a.title || a.url : a.filename))
            .filter((s): s is string => Boolean(s))
        )
      ),
    ];
    if (sources.length > 0) {
      return { type: "trace", label: `Sources: ${sources.join(", ")}`, status: "completed" };
    }
  }
  return null;
}

/**
 * `response.output_text.done` and `response.file_search_call.searching` are
 * intentionally NOT mapped: Foundry's Responses API re-sends the complete
 * answer text on `.done` after already streaming it via `.delta` (mapping it
 * duplicated every reply), and fires both `.in_progress` and `.searching` for
 * one search step (mapping both duplicated the "Searching…" trace line).
 */
export function mapFoundryEvent(event: FoundryStreamEvent): FoundryServerEvent | null {
  switch (event.type) {
    case "response.output_text.delta": {
      const delta = extractTextDelta((event as Record<string, unknown>).delta);
      return delta ? { type: "text-delta", delta } : null;
    }
    case "response.file_search_call.in_progress":
      return { type: "trace", label: FILE_SEARCH_LABEL, status: "in_progress" };
    case "response.output_item.done":
      return mapOutputItemDone(event as OutputItemDoneEvent);
    case "response.completed":
      return { type: "done" };
    case "response.error":
      return { type: "error", message: String((event as { message?: unknown }).message ?? "Unknown error") };
    default:
      return null;
  }
}

export async function createFoundryStreamResponse(opts: {
  projectEndpoint: string;
  agentName: string;
  messages: UIMessage[];
  conversationId: string | null;
  responseHeaders: Record<string, string>;
  signal?: AbortSignal;
  openAIClientFactory?: (projectEndpoint: string) => OpenAIResponsesClientLike;
}): Promise<Response> {
  const message = lastUserMessageText(opts.messages);
  const openai = (opts.openAIClientFactory ?? defaultOpenAIClientFactory)(opts.projectEndpoint);

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "foundry error"),
    execute: async ({ writer }) => {
      const textId = "assistant-main";
      let textOpen = false;
      const openText = () => {
        if (!textOpen) {
          writer.write({ type: "text-start", id: textId });
          textOpen = true;
        }
      };
      const closeText = () => {
        if (textOpen) {
          writer.write({ type: "text-end", id: textId });
          textOpen = false;
        }
      };

      if (opts.signal?.aborted) return;

      try {
        let conversationId = opts.conversationId;
        if (!conversationId) {
          const conversation = await openai.conversations.create();
          conversationId = conversation.id;
          writer.write({
            type: "data-externalConversation",
            id: "foundry-conversation",
            data: { conversationId },
          });
        }

        const responseStream = await openai.responses.create(
          { conversation: conversationId, input: message, stream: true },
          {
            signal: opts.signal,
            body: { agent_reference: { name: opts.agentName, type: "agent_reference" } },
          }
        );

        let traceSeq = 0;
        for await (const event of responseStream) {
          const mapped = mapFoundryEvent(event);
          if (!mapped) continue;
          if (mapped.type === "text-delta") {
            openText();
            writer.write({ type: "text-delta", id: textId, delta: mapped.delta });
          } else if (mapped.type === "trace") {
            writer.write({
              type: "data-digigraphTrace",
              id: `foundry-trace-${traceSeq++}`,
              data: {
                v: 1,
                type: "external_activity",
                service: "external",
                payload: { label: mapped.label, status: mapped.status },
              },
            });
          } else if (mapped.type === "error") {
            throw new Error(mapped.message);
          } else if (mapped.type === "done") {
            break;
          }
        }
      } catch (err) {
        if (opts.signal?.aborted) return;
        openText();
        writer.write({
          type: "text-delta",
          id: textId,
          delta: `Upstream error: ${err instanceof Error ? err.message : String(err)}`,
        });
      } finally {
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
