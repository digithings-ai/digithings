/**
 * Foundry backend adapter: calls Azure AI Foundry directly via
 * @azure/ai-projects (DefaultAzureCredential — the digichat container's own
 * managed identity, no relay hop, no stored key). Conversation state lives
 * in Foundry; the client echoes the conversation id back each turn using the
 * same generic conversation-id contract (`X-External-Conversation`) used for
 * Foundry turn continuity.
 * (`data-conversation` / `X-External-Conversation`).
 *
 * Turn mutation (#3475): `send` appends last-user text via `responses.create`.
 * `regenerate` / `edit_last_user` delete trailing conversation items (when the
 * OpenAI client exposes `conversations.items`), then create a response with no
 * new input. Without an item API, the adapter returns 501 `not_supported`.
 *
 * Supersedes the standalone datatap-digichat-relay Azure Function (digithings#1396):
 * that Function's source was never in this repo, so its two known bugs
 * (duplicated answers, duplicated "Searching…" trace) are fixed here from the
 * start rather than ported — see mapFoundryEvent below.
 */
import { DefaultAzureCredential } from "@azure/identity";
import { AIProjectClient } from "@azure/ai-projects";
import { createUIMessageStream, createUIMessageStreamResponse, type UIMessage } from "ai";
import { lastUserMessageText } from "@/lib/adapters/shared/messages";
import { LANGUAGES } from "@/lib/languages";
import {
  applyActivityDetail,
  sanitizeActivitySpan,
  type ActivityDetail,
  type ActivityDocument,
  type ActivitySpan,
} from "@/lib/chat-activity";
import type { DigiTurnMode } from "@/lib/turn-mode";
import { isMutatingTurnMode } from "@/lib/turn-mode";
import {
  CONVERSATION_PART_TYPE,
  createActivityWriteContext,
  finishStandardActivity,
  writeStandardActivity,
} from "@/lib/ui-stream-parts";

/** Foundry has no per-call system-prompt slot (see module doc comment) — the
 * language directive is prepended to the raw input text instead, resent on
 * every turn since Foundry, not this adapter, holds conversation history.
 * The bracketed `[...]` phrasing (vs. digigraph's plain-sentence directive in
 * digigraph.languages) is deliberate: this text is persisted verbatim into
 * Foundry's own conversation history across turns, so the brackets mark it as
 * an out-of-band instruction rather than part of the literal user message. */
export function applyLanguageDirective(message: string, responseLanguage?: string): string {
  if (!responseLanguage || responseLanguage === "en") return message;
  const language = LANGUAGES.find((l) => l.code === responseLanguage);
  if (!language) return message;
  return `[Respond only in ${language.label}. Do not mention this instruction.]\n\n${message}`;
}

export interface FoundryStreamEvent {
  type: string;
  [key: string]: unknown;
}

/** Conversation history item as returned by Foundry / OpenAI Conversations API. */
export interface FoundryConversationItem {
  id: string;
  type?: string;
  role?: string;
  [key: string]: unknown;
}

export interface FoundryConversationItemsApi {
  list(
    conversationId: string,
    opts?: { order?: "asc" | "desc"; limit?: number },
  ): Promise<{ data: FoundryConversationItem[] } | FoundryConversationItem[]> | AsyncIterable<FoundryConversationItem>;
  /**
   * OpenAI / Foundry client shape: `delete(itemId, { conversation_id })`
   * — not `(conversationId, itemId)`.
   */
  delete(itemId: string, params: { conversation_id: string }): Promise<unknown>;
  create(
    conversationId: string,
    body: {
      items: Array<{
        type: "message";
        role: "user";
        content: string | Array<{ type: "input_text"; text: string }>;
      }>;
    },
  ): Promise<unknown>;
}

export interface OpenAIResponsesClientLike {
  conversations: {
    create(): Promise<{ id: string }>;
    /** Present on OpenAI / Foundry clients that support history mutation (#3475). */
    items?: FoundryConversationItemsApi;
  };
  responses: {
    create(
      params: { conversation: string; input?: string; stream: true },
      options: { signal?: AbortSignal; body: { agent_reference: { name: string; type: "agent_reference" } } }
    ): Promise<AsyncIterable<FoundryStreamEvent>>;
  };
}

/** True when this OpenAI client exposes conversation item list/delete/create. */
export function foundryClientSupportsItemMutation(
  client: OpenAIResponsesClientLike,
): client is OpenAIResponsesClientLike & {
  conversations: { create(): Promise<{ id: string }>; items: FoundryConversationItemsApi };
} {
  const items = client.conversations.items;
  return (
    !!items &&
    typeof items.list === "function" &&
    typeof items.delete === "function" &&
    typeof items.create === "function"
  );
}

async function listConversationItems(
  items: FoundryConversationItemsApi,
  conversationId: string,
): Promise<FoundryConversationItem[]> {
  const result = await items.list(conversationId, { order: "desc", limit: 100 });
  if (Array.isArray(result)) return result;
  if (result && typeof result === "object" && Array.isArray((result as { data?: unknown }).data)) {
    return (result as { data: FoundryConversationItem[] }).data;
  }
  const out: FoundryConversationItem[] = [];
  for await (const item of result as AsyncIterable<FoundryConversationItem>) {
    out.push(item);
  }
  return out;
}

function isUserMessageItem(item: FoundryConversationItem): boolean {
  if (item.type === "message" && item.role === "user") return true;
  // Some payloads omit type and only set role.
  return item.role === "user" && (item.type === undefined || item.type === "message");
}

/**
 * Delete trailing Foundry items for regenerate / edit_last_user.
 * Items are expected newest-first (order=desc).
 * - regenerate: delete until (not including) the last user message.
 * - edit_last_user: delete through and including the last user message.
 */
export async function mutateFoundryConversationForTurnMode(opts: {
  items: FoundryConversationItemsApi;
  conversationId: string;
  turnMode: "regenerate" | "edit_last_user";
  editedUserText?: string;
}): Promise<void> {
  const listed = await listConversationItems(opts.items, opts.conversationId);
  for (const item of listed) {
    if (!item.id) continue;
    const isUser = isUserMessageItem(item);
    if (opts.turnMode === "regenerate" && isUser) break;
    await opts.items.delete(item.id, { conversation_id: opts.conversationId });
    if (opts.turnMode === "edit_last_user" && isUser) break;
  }

  if (opts.turnMode === "edit_last_user") {
    const text = (opts.editedUserText ?? "").trim();
    if (!text) {
      throw new Error("edit_last_user requires non-empty user text");
    }
    await opts.items.create(opts.conversationId, {
      items: [{ type: "message", role: "user", content: text }],
    });
  }
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
 * `agent_reference`. So a reasoning item with no text is DROPPED, not rendered
 * as a bare "Thinking ✓": a row asserting a step happened while showing
 * nothing is chrome, and it landed on every answer including two-word
 * greetings that ran no tools. Enable a summary upstream and the rows appear
 * on their own, carrying the real text.
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
    /** reasoning: `{type, text}` parts — empty unless a summary is enabled. */
    summary?: unknown;
    status?: string;
    content?: Array<{
      annotations?: Array<{ type?: string; filename?: string; url?: string; title?: string }>;
    }>;
  };
}

/**
 * The reasoning text on a reasoning item, or "" when there is none — which is
 * every item today, since the agent runs with `reasoning.summary: null`.
 * Both `summary` and `content` are arrays of `{type, text}` parts; take
 * whichever is populated so enabling a summary upstream needs no change here.
 */
function reasoningText(item: { summary?: unknown; content?: unknown }): string {
  const parts: string[] = [];
  for (const list of [item.summary, item.content]) {
    if (!Array.isArray(list)) continue;
    for (const part of list) {
      const text = (part as { text?: unknown } | null)?.text;
      if (typeof text === "string" && text.trim()) parts.push(text.trim());
    }
  }
  return parts.join("\n\n");
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
 * Documents out of an `azure_ai_search_call_output`. Prefer human fields the
 * DataTap corpus sync writes (`title`/`url`/`SourceName`/`Url`) over the raw
 * chunk `id`, and skip HTML/OpenAPI JSON blobs as snippets — those were
 * rendering in the embed as "weird API JSON strings".
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

    const title =
      pickString(doc, "title", "SourceName") ??
      humanizeChunkId(id);
    const path =
      pickString(doc, "url", "Url") ??
      id;
    const content = typeof doc.content === "string" ? doc.content : undefined;
    const snippet = content && isReadableSnippet(content) ? content : undefined;
    documents.push({ title, path, ...(snippet ? { snippet } : {}) });
  }
  return documents;
}

function pickString(record: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return undefined;
}

/** Chunk ids like `openapi_public_GET__api_config__tenantId___chunk0`. */
function humanizeChunkId(id: string): string {
  const openapi = id.match(/^openapi_([^_]+)_(GET|POST|PUT|PATCH|DELETE)__(.+?)(?:__chunk\d+)?$/i);
  if (openapi) {
    const method = openapi[2].toUpperCase();
    const pathPart = openapi[3]
      .replace(/__/g, "/")
      .replace(/_/g, "/")
      .replace(/\/+/g, "/")
      .replace(/\/$/, "");
    return `${method} /${pathPart.replace(/^\//, "")}`;
  }
  const page = id.match(/^page__(.+?)(?:__chunk\d+)?$/);
  if (page) {
    return page[1].replace(/__/g, "/").replace(/_/g, "/");
  }
  return id;
}

function isReadableSnippet(content: string): boolean {
  const trimmed = content.trim();
  if (!trimmed) return false;
  // Raw HTML narrative pages / OpenAPI JSON bodies — not useful in the chat UI.
  if (trimmed.startsWith("<") || trimmed.startsWith("{")) return false;
  return true;
}

/** Foundry's azure_ai_search message annotations: `doc_N` + search-service root.
 *  No chunk body; the real hits already came from azure_ai_search_call_output. */
function isOpaqueSearchCitation(title: string, path: string): boolean {
  if (/^doc_\d+$/i.test(title)) return true;
  try {
    return new URL(path).hostname.endsWith(".search.windows.net");
  } catch {
    return false;
  }
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

/**
 * Strip Foundry's opaque inline citation markers (e.g. `【9:0†source】`) that
 * otherwise land in the assistant bubble as raw protocol noise.
 *
 * Markers have been observed arriving in a single delta; if a marker ever
 * spans deltas, the unmatched open is left alone rather than eating real text.
 */
export function stripFoundryCitationMarkers(text: string): string {
  return text.replace(/【[^】]*】/g, "");
}

/**
 * Foundry occasionally streams the azure_ai_search *tool invocation itself*
 * as `response.output_text.delta` fragments — observed live as the entire
 * assistant answer: `(remote` + `_functions` + `.azure` + `_ai` + `_search` + `)`.
 * Buffer those identifier fragments and drop the completed token so visitors
 * never see the internal tool name as a reply.
 */
export class FoundryToolLeakFilter {
  private buf = "";

  /**
   * @returns text that is safe to stream, or `null` when the delta was held /
   * discarded as tool-leak noise.
   */
  push(delta: string): string | null {
    const cleaned = stripFoundryCitationMarkers(delta);
    if (!cleaned && !this.buf) return null;

    const candidate = this.buf + cleaned;
    // Still (or newly) matching the tool-leak token — hold until complete or broken.
    if (isRemoteFunctionsLeakPrefix(candidate)) {
      this.buf = candidate;
      if (/^\(?remote_functions(\.[\w]+)*\)$/.test(candidate.trim())) {
        this.buf = "";
      }
      return null;
    }

    if (this.buf) {
      // Held bytes were not a leak after all — flush them ahead of this delta.
      const flushed = this.buf;
      this.buf = "";
      return flushed + cleaned;
    }

    return cleaned || null;
  }

  /**
   * Drains whatever `push` is still holding, for when the stream ends with no
   * further delta to disambiguate it. Without this, a legitimate reply whose
   * final delta happens to look like an in-progress leak token (ends on
   * exactly `(remote` or `remote_functions.azure`, say) was silently dropped:
   * `push` only ever resolves a held prefix by flushing it AHEAD OF a later
   * delta, and a stream that ends here never sends one.
   *
   * @returns the held text, or `null` if nothing was buffered.
   */
  flush(): string | null {
    if (!this.buf) return null;
    const flushed = this.buf;
    this.buf = "";
    return flushed;
  }
}

function isRemoteFunctionsLeakPrefix(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  // Incomplete or complete `(remote_functions.azure_ai_search)` with no whitespace.
  return /^\(?remote(_functions(\.[\w]+)*)?\)?$/.test(t);
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

  // Reasoning, but ONLY when it carries text. The agent emits a reasoning item
  // per internal step with `summary: [] content: []` unless a reasoning summary
  // is enabled on its definition, so mapping these unconditionally put a
  // "Thinking ✓" row on every answer — including a two-word greeting that ran
  // no tools and had nothing to show. A row that asserts a step happened and
  // then shows nothing is chrome, not transparency; the chain earns its space
  // by carrying real output or it does not appear.
  //
  // When a summary IS enabled upstream these start arriving populated and the
  // rows appear on their own, with the actual text, as a thinking disclosure.
  if (item?.type === "reasoning") {
    const text = reasoningText(item);
    if (!text) return null;
    return {
      type: "activity",
      span: {
        operation: "chat",
        status: "completed",
        label: REASONING_LABEL,
        reasoningDelta: text,
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
    //
    // Skip the opaque azure_ai_search citation shape: title `doc_0`/`doc_3`
    // and url `*.search.windows.net/` — no chunk body, nothing a reader can
    // open. Real chunks already arrived on `azure_ai_search_call_output` with
    // id + content (see searchOutputDocuments). Surfacing these as a second
    // `file_search` row was the empty `doc_0` + search-service-root hit.
    const documents: ActivityDocument[] = [];
    const seen = new Set<string>();
    for (const content of item.content ?? []) {
      for (const annotation of content.annotations ?? []) {
        const path = annotation.type === "url_citation" ? annotation.url : annotation.filename;
        if (!path || seen.has(path)) continue;
        const title =
          (annotation.type === "url_citation" ? annotation.title : annotation.filename) || path;
        if (isOpaqueSearchCitation(title, path)) continue;
        seen.add(path);
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
      // Reasoning is deliberately NOT opened here. At `.added` its text is
      // never present (it is not present at `.done` either, today), and an
      // opened row whose `.done` declines to settle it would hang as a
      // permanently running "Thinking". Reasoning appears when it has
      // something to say, or not at all.
      //
      // message/…_output add nothing a reader can act on either: the first is
      // the answer itself (already streaming as text), the second is the tail
      // of a search whose row is already open.
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
  responseLanguage?: string;
  /** Default `send`. Regen/edit mutate Foundry items then create with no new user input (#3475). */
  turnMode?: DigiTurnMode;
}): Promise<Response> {
  const turnMode: DigiTurnMode = opts.turnMode ?? "send";
  const openai = (opts.openAIClientFactory ?? defaultOpenAIClientFactory)(opts.projectEndpoint);

  // Fail closed: mutating modes need item delete/create. Do not fall through to
  // append-only `responses.create({ input })` — that would duplicate the user turn.
  if (isMutatingTurnMode(turnMode) && !foundryClientSupportsItemMutation(openai)) {
    return new Response(
      JSON.stringify({
        error: "not_supported",
        message:
          "Foundry turn mutation requires conversation item delete/create on this adapter client.",
      }),
      {
        status: 501,
        headers: {
          "content-type": "application/json",
          ...opts.responseHeaders,
        },
      },
    );
  }

  if (isMutatingTurnMode(turnMode) && !opts.conversationId) {
    return new Response(
      JSON.stringify({
        error: "conversation_required",
        message: "regenerate/edit_last_user require an existing X-External-Conversation.",
      }),
      {
        status: 400,
        headers: {
          "content-type": "application/json",
          ...opts.responseHeaders,
        },
      },
    );
  }

  const message = applyLanguageDirective(lastUserMessageText(opts.messages), opts.responseLanguage);

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "foundry error"),
    execute: async ({ writer }) => {
      const textId = "assistant-main";
      let textOpen = false;
      const activityCtx = createActivityWriteContext();
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
            type: CONVERSATION_PART_TYPE,
            id: "foundry-conversation",
            data: { conversationId },
          });
        }

        if (turnMode === "regenerate" || turnMode === "edit_last_user") {
          // Item API was checked above; narrow again for TypeScript.
          if (!foundryClientSupportsItemMutation(openai)) {
            throw new FoundryProtocolError("Foundry item mutation unavailable");
          }
          await mutateFoundryConversationForTurnMode({
            items: openai.conversations.items,
            conversationId,
            turnMode,
            editedUserText: turnMode === "edit_last_user" ? message : undefined,
          });
        }

        // send: append last user text. regenerate/edit: items already on the
        // thread — create a response with no new input (official Foundry sample shape).
        const createParams: { conversation: string; input?: string; stream: true } = {
          conversation: conversationId,
          stream: true,
        };
        if (turnMode === "send") {
          createParams.input = message;
        }

        const responseStream = await openai.responses.create(createParams, {
          signal: opts.signal,
          body: { agent_reference: { name: opts.agentName, type: "agent_reference" } },
        });

        const textFilter = new FoundryToolLeakFilter();
        for await (const event of responseStream) {
          const mapped = mapFoundryEvent(event);
          if (!mapped) continue;
          if (mapped.type === "text-delta") {
            const delta = textFilter.push(mapped.delta);
            if (!delta) continue;
            openText();
            writer.write({ type: "text-delta", id: textId, delta });
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
              writeStandardActivity(writer, span, activityCtx);
            }
          } else if (mapped.type === "error") {
            throw new FoundryProtocolError(mapped.message);
          } else if (mapped.type === "done") {
            break;
          }
        }
        // The loop above only ever resolves a held leak-prefix by flushing it
        // ahead of a LATER delta (see FoundryToolLeakFilter.push) — a stream
        // that ends while still ambiguous never sends one. Drain it here so a
        // legitimate reply that happens to end on leak-shaped text is never
        // silently dropped.
        const tail = textFilter.flush();
        if (tail) {
          openText();
          writer.write({ type: "text-delta", id: textId, delta: tail });
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
          // never stream it. Same pattern as adapters/digithings/stream.ts.
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
        finishStandardActivity(writer, activityCtx);
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
