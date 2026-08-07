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
import {
  ACTIVITY_PART_TYPE,
  applyActivityDetail,
  sanitizeActivitySpan,
  type ActivityDetail,
  type ActivityDocument,
  type ActivitySpan,
} from "./chat-activity";

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
  | { type: "activity"; span: ActivitySpan }
  | { type: "done" }
  | { type: "error"; message: string };

/**
 * Marks an error surfaced deliberately by Foundry's own `response.error`
 * protocol event, as opposed to an unexpected SDK/network exception. The
 * former is already a presentation-safe message meant to be shown; the
 * latter can carry stack traces or internal hostnames and must be masked —
 * see the catch block below.
 */
class FoundryProtocolError extends Error {}

const FILE_SEARCH_LABEL = "Searching knowledge base…";

/**
 * What this agent ACTUALLY emits, recorded off the live DataTap agent across
 * four question shapes (docs lookup, news, multi-step reasoning, greeting).
 * Every `response.output_item.done` carried one of exactly four item types:
 *
 *   reasoning                    23   — always summary:[] content:[] (see below)
 *   azure_ai_search_call         10   — `arguments` is JSON: {"query": "..."}
 *   azure_ai_search_call_output  10   — `output` is JSON: {"documents":[{id,content}]}
 *   message                       4   — annotations → citations
 *
 * Two things that look like they should exist and do not:
 *
 * - **`file_search_call` never fires for this agent.** It is wired to the
 *   `azure_ai_search` tool, so the file_search branches below are dead for
 *   DataTap. They are kept because a Foundry agent using the native
 *   file_search tool does emit them, and both shapes are legitimate.
 * - **There is no web-search tool.** "What is the latest news…" still routed
 *   to azure_ai_search. Do not render a web-search row that cannot happen.
 *
 * And the reason reasoning rows carry no text: the request echoes
 * `reasoning: {..., summary: null}`, and asking for one is refused —
 * `400 Not allowed when agent is specified` for "auto" / "concise" /
 * "detailed" alike. A reasoning SUMMARY has to be enabled on the agent
 * definition in Foundry; it cannot be requested per-call alongside
 * `agent_reference`. So a reasoning item is rendered as the fact that a step
 * happened, never as invented text.
 */
const SEARCH_TOOL = "azure_ai_search";
const SEARCH_LABEL = "Searching the knowledge base…";
const REASONING_LABEL = "Thinking";

interface OutputItemDoneEvent extends FoundryStreamEvent {
  item?: {
    type?: string;
    queries?: string[];
    /** azure_ai_search_call: JSON string, `{"query": "..."}`. */
    arguments?: string;
    /** azure_ai_search_call_output: JSON string, `{"documents":[…]}`. */
    output?: string;
    status?: string;
    content?: Array<{
      annotations?: Array<{ type?: string; filename?: string; url?: string; title?: string }>;
    }>;
  };
}

/** `arguments`/`output` arrive as JSON strings; a malformed one must not throw. */
function parseJsonObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "string") return null;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/**
 * Documents out of an `azure_ai_search_call_output`. The chunks carry an `id`
 * and the retrieved `content`, which is strictly better than the `message`
 * annotations for the same search: those come back titled `doc_0`/`doc_3` with
 * every url pointing at the search service root, which names nothing a reader
 * can act on. `id` at least identifies the chunk it came from.
 */
function searchOutputDocuments(raw: unknown): ActivityDocument[] {
  const parsed = parseJsonObject(raw);
  const list = parsed?.documents;
  if (!Array.isArray(list)) return [];
  const documents: ActivityDocument[] = [];
  const seen = new Set<string>();
  for (const entry of list) {
    if (!entry || typeof entry !== "object") continue;
    const doc = entry as Record<string, unknown>;
    const id = typeof doc.id === "string" ? doc.id : undefined;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const content = typeof doc.content === "string" ? doc.content : undefined;
    documents.push({ title: id, path: id, ...(content ? { snippet: content } : {}) });
  }
  return documents;
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

  // The tool this agent actually calls. `arguments` is the model's own search
  // query — the tool INPUT a reader wants to see, and the only honest label
  // for what is happening while it runs.
  if (item?.type === "azure_ai_search_call") {
    const query = parseJsonObject(item.arguments)?.query;
    const q = typeof query === "string" && query.trim() ? query.trim() : undefined;
    return {
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: SEARCH_TOOL,
        status: item.status === "failed" ? "failed" : "completed",
        ...(q ? { query: q } : {}),
        label: q ? `Searched for: "${q}"` : SEARCH_LABEL,
      },
    };
  }

  // The tool OUTPUT: the chunks the search returned.
  if (item?.type === "azure_ai_search_call_output") {
    const documents = searchOutputDocuments(item.output);
    return {
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: SEARCH_TOOL,
        status: item.status === "failed" ? "failed" : "completed",
        label: "Sources",
        ...(documents.length ? { documents } : {}),
      },
    };
  }

  // A reasoning step happened. Its text is NOT available (see the docblock
  // above), so this row asserts only that the model thought — never a
  // fabricated summary of what it thought.
  if (item?.type === "reasoning") {
    return {
      type: "activity",
      span: {
        operation: "chat",
        status: "completed",
        label: REASONING_LABEL,
      },
    };
  }

  if (item?.type === "file_search_call") {
    const queries = item.queries ?? [];
    const query = queries[0];
    const label = query
      ? `Searched for: ${queries.map((q) => `"${q}"`).join(", ")}`
      : FILE_SEARCH_LABEL;
    return {
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: "file_search",
        status: "completed",
        ...(query ? { query } : {}),
        label,
      },
    };
  }
  if (item?.type === "message") {
    // Two citation shapes share this event: Foundry's native file_search tool
    // annotates with `filename`, while the azure_ai_search tool emits
    // `{type: "url_citation", url, title}` with no filename at all. Handle both
    // so sources show up regardless of which grounding tool an agent uses.
    const documents: ActivityDocument[] = [];
    const seen = new Set<string>();
    for (const content of item.content ?? []) {
      for (const annotation of content.annotations ?? []) {
        const path = annotation.type === "url_citation" ? annotation.url : annotation.filename;
        if (!path || seen.has(path)) continue;
        seen.add(path);
        const title =
          (annotation.type === "url_citation" ? annotation.title : annotation.filename) || path;
        documents.push({ title, path });
      }
    }
    if (documents.length > 0) {
      return {
        type: "activity",
        span: {
          operation: "retrieve",
          toolName: "file_search",
          status: "completed",
          label: "Sources",
          documents,
        },
      };
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
      return {
        type: "activity",
        span: {
          operation: "execute_tool",
          toolName: "file_search",
          status: "started",
          label: FILE_SEARCH_LABEL,
        },
      };
    // The live half. At `.added` the call exists but `arguments` is still ""
    // (observed), so a started span can name the tool but not yet the query —
    // which is precisely the contract toDigiChatActivity's `pendingRow`
    // expects: it opens one placeholder per tool name and the matching
    // `.done` fills the query into that same row rather than opening a second.
    // Without this the chain only ever appeared after the work had finished.
    case "response.output_item.added": {
      const item = (event as OutputItemDoneEvent).item;
      if (item?.type === "azure_ai_search_call") {
        return {
          type: "activity",
          span: {
            operation: "execute_tool",
            toolName: SEARCH_TOOL,
            status: "started",
            label: SEARCH_LABEL,
          },
        };
      }
      if (item?.type === "reasoning") {
        return {
          type: "activity",
          span: { operation: "chat", status: "started", label: REASONING_LABEL },
        };
      }
      // message/…_output add nothing a reader can act on: the first is the
      // answer itself (already streaming as text), the second is the tail of
      // a search whose row is open.
      return null;
    }
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
  activityDetail: ActivityDetail;
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
          } else if (mapped.type === "activity") {
            // Foundry's own event carries unbounded upstream strings (a query
            // list, citation titles/urls); the digigraph and relay providers
            // cap theirs before writing (see chatActivitySpan) but this path
            // built the span literal directly and never did. Route it through
            // the same allowlist/cap the client applies on receipt, so an
            // oversized or over-long upstream payload never reaches the wire
            // in the first place.
            const sanitized = sanitizeActivitySpan(mapped.span);
            const span = sanitized && applyActivityDetail(sanitized, opts.activityDetail);
            if (span) {
              writer.write({
                type: ACTIVITY_PART_TYPE,
                id: `foundry-activity-${traceSeq++}`,
                data: span,
              });
            }
          } else if (mapped.type === "error") {
            throw new FoundryProtocolError(mapped.message);
          } else if (mapped.type === "done") {
            break;
          }
        }
      } catch (err) {
        if (opts.signal?.aborted) return;
        openText();
        if (err instanceof FoundryProtocolError) {
          writer.write({
            type: "text-delta",
            id: textId,
            delta: `Upstream error: ${err.message}`,
          });
        } else {
          // An unexpected SDK/network exception, not Foundry's own protocol
          // error — can carry stack traces or internal hostnames, and this
          // response reaches anonymous embed visitors. Log it server-side;
          // never stream it. Same pattern as stream-digigraph-trace.ts and
          // external-relay-stream.ts.
          console.error(
            "[foundry] stream error",
            err instanceof Error ? err.message : String(err)
          );
          writer.write({
            type: "text-delta",
            id: textId,
            delta: "The assistant is unavailable right now. Please try again shortly.",
          });
        }
      } finally {
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
