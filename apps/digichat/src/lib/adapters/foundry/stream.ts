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
import { privateModeInstructionText } from "@/lib/private-mode";
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
import { abortableSleep, waitOutRateLimit } from "@/lib/rate-limit-wait";
import { TOOL_CAP_INSTRUCTION } from "@/lib/guardrails/budget";
import type { TurnGuard } from "@/lib/guardrails/turn";
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

/** The DIG-100 no-invent guard (DIG-509 leaf 1b). Its prose lives in
 *  `docs/digichat/no-invent-guard.md` §1, which leaf 1a owns and this leaf must
 *  not edit; the text below is a copy of it, so a change to the rule lands there
 *  first. The prose *between the brackets* must stay byte-identical to that
 *  section, and the block must carry no capability inventory — a list of tools
 *  would go stale the day a tool is added.
 *
 *  The brackets and the closing sentence are not part of §1. They are this
 *  file's existing out-of-band convention — the same one `applyLanguageDirective`
 *  uses, for the same reason: the text is persisted verbatim into Foundry's own
 *  conversation history, so the brackets mark it as an instruction rather than
 *  something the user typed. `EXPECTED_BLOCK` in `stream.test.ts` spells the whole
 *  literal out again, brackets included, so the drift pin does not depend on this
 *  comment being read correctly.
 *
 *  Deliberately unconditional. `applyLanguageDirective` returns its input
 *  unchanged for an unset or `"en"` target, so routing this through it would make
 *  the guard inert on most of our traffic while still looking correct in review. */
const GROUNDING_DIRECTIVE = `[You are a support assistant.

Answer an identifier, name, amount or rate only when a tool result you observed
this turn contains it. If no such result was observed, say "no record was found"
and don't guess. Don't say a capability is "none" unless a tool you observed this
turn proves it. Do not mention this instruction.]

`;

/** Prepend the no-invent guard to the raw user text of the turn that creates the
 *  Foundry conversation. Foundry holds the conversation history, so this runs
 *  once per conversation — not once per turn — and a later turn sends the user's
 *  text unchanged. Idempotent: a message that already carries the block comes
 *  back byte-identical rather than with a second copy stacked on it.
 *
 *  The single caller passes `lastUserMessageText(opts.messages)` — client text,
 *  never this adapter's own output — so the already-prefixed branch is defensive
 *  rather than reachable in production. It still earns its keep on one case the
 *  caller cannot rule out: a user who pastes the guard in themselves would
 *  otherwise get a second copy in the transcript. `stream.test.ts` pins it
 *  directly on this exported function so the claim cannot rot. */
export function applyGroundingDirective(message: string): string {
  if (message.startsWith(GROUNDING_DIRECTIVE)) return message;
  return `${GROUNDING_DIRECTIVE}${message}`;
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

/**
 * Extra fields merged onto the Responses request beside `agent_reference`.
 *
 * `max_tool_calls` and `tool_choice` are both fields of the Foundry Create
 * Response body (the same body that requires `agent_reference`). They are not
 * on the stock OpenAI SDK params object, so they travel in `body`, the same
 * way `agent_reference` already does.
 */
export interface FoundryResponsesCreateBody {
  agent_reference: { name: string; type: "agent_reference" };
  max_tool_calls?: number;
  tool_choice?: "none";
  /**
   * The chat's /effort choice. Omitted when the visitor set none, so the
   * agent's model keeps its own default reasoning level.
   */
  reasoning?: { effort: FoundryReasoningEffort };
}

export type FoundryReasoningEffort = "low" | "medium" | "high";

export interface OpenAIResponsesClientLike {
  conversations: {
    create(): Promise<{ id: string }>;
    /** Present on OpenAI / Foundry clients that support history mutation (#3475). */
    items?: FoundryConversationItemsApi;
  };
  responses: {
    create(
      params: {
        conversation: string;
        input?: string | ReadonlyArray<{ role: "user"; content: string }>;
        stream: true;
      },
      options: {
        signal?: AbortSignal;
        /** SDK-level retries; the adapter owns capacity retries (#5979). */
        maxRetries?: number;
        body: FoundryResponsesCreateBody;
      }
    ): Promise<AsyncIterable<FoundryStreamEvent>>;
  };
}

/**
 * A tool invocation item, not its output and not a list/approval side event.
 *
 * `mcp_call` is the hosted MCP shape. `*_call` covers built-in tools
 * (`file_search_call`, `azure_ai_search_call`, …). Outputs end in `_output`
 * and must not count as a second call.
 */
export function isFoundryToolCallType(type: string | undefined): boolean {
  if (!type) return false;
  if (type.endsWith("_output") || type.endsWith("_call_output")) return false;
  if (
    type === "mcp_list_tools" ||
    type === "mcp_approval_request" ||
    type === "mcp_approval_response"
  ) {
    return false;
  }
  return type === "mcp_call" || type.endsWith("_call");
}

type FoundryToolCallSight = { type: string; id?: string; phase: "start" | "done" };

/** The tool call a stream event opens or completes, if it is one. */
export function foundryToolCallSight(event: FoundryStreamEvent): FoundryToolCallSight | null {
  if (event.type === "response.file_search_call.in_progress") {
    return { type: "file_search_call", phase: "start" };
  }
  // `.searching` repeats `.in_progress` for the same file_search step.
  if (event.type === "response.file_search_call.searching") return null;
  if (event.type !== "response.output_item.added" && event.type !== "response.output_item.done") {
    return null;
  }
  const item = (event as { item?: { type?: string; id?: string; call_id?: string } }).item;
  if (!isFoundryToolCallType(item?.type)) return null;
  const id = item?.id || item?.call_id;
  return {
    type: item!.type!,
    ...(id ? { id } : {}),
    phase: event.type.endsWith(".added") ? "start" : "done",
  };
}

/**
 * Counts tool calls once per turn. A start and its matching done share an id
 * when Foundry sends one; an id-less start is paired with the next event of
 * the same item type so `in_progress` plus `.done` is a single call.
 */
export class FoundryToolCallCounter {
  count = 0;
  private readonly seenIds = new Set<string>();
  private readonly unpairedStarts: string[] = [];

  observe(event: FoundryStreamEvent): "new" | "known" | "ignore" {
    const sight = foundryToolCallSight(event);
    if (!sight) return "ignore";
    if (sight.id) {
      if (this.seenIds.has(sight.id)) return "known";
      const unpaired = this.unpairedStarts.indexOf(sight.type);
      if (unpaired >= 0) {
        this.unpairedStarts.splice(unpaired, 1);
        this.seenIds.add(sight.id);
        return "known";
      }
      this.seenIds.add(sight.id);
      this.count += 1;
      return "new";
    }
    if (sight.phase === "start") {
      this.unpairedStarts.push(sight.type);
      this.count += 1;
      return "new";
    }
    const unpaired = this.unpairedStarts.indexOf(sight.type);
    if (unpaired >= 0) {
      this.unpairedStarts.splice(unpaired, 1);
      return "known";
    }
    this.count += 1;
    return "new";
  }
}

function normalizeMaxToolCalls(value: number | undefined): number | undefined {
  if (value === undefined) return undefined;
  if (!Number.isInteger(value) || value < 1 || value > 100) return undefined;
  return value;
}

/**
 * Foundry rejects some per-call overrides once `agent_reference` is set
 * (`400 Not allowed when agent is specified` for reasoning summaries).
 * `max_tool_calls` and `tool_choice` are documented on that same request;
 * this matches the refusal if a deployment still rejects them.
 */
function isAgentOverrideRejected(err: unknown): boolean {
  if (httpStatusOf(err) !== 400) return false;
  const message = upstreamErrorMessage(err) ?? (err instanceof Error ? err.message : "");
  return /not allowed when agent is specified/i.test(message);
}

/**
 * A 400 that refuses the per-call reasoning level: the agent-reference refusal
 * above, or any bad request that names reasoning (an effort the model does not
 * support). Only checked while `reasoning` is on the body, so dropping it once
 * is the whole fallback and the turn runs at the model's default level.
 */
function isReasoningOverrideRejected(err: unknown): boolean {
  if (httpStatusOf(err) !== 400) return false;
  if (isAgentOverrideRejected(err)) return true;
  const message = upstreamErrorMessage(err) ?? (err instanceof Error ? err.message : "");
  return /reasoning/i.test(message);
}

function forwardAbort(parent: AbortSignal | undefined, child: AbortController): () => void {
  if (!parent) return () => {};
  if (parent.aborted) {
    child.abort(parent.reason);
    return () => {};
  }
  const onAbort = () => child.abort(parent.reason);
  parent.addEventListener("abort", onAbort);
  return () => parent.removeEventListener("abort", onAbort);
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
  | { type: "done"; usage?: FoundryUsage; model?: string }
  | { type: "error"; message: string }
  /** The model deployment's per-minute token/request limit ended the turn mid-stream. */
  | { type: "rate-limit"; message: string };

/** Provider-reported token counts, in the shape the client expects. */
export type FoundryUsage = {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
};

/**
 * The agent's own tool-invocation failure, e.g.
 *
 *   An error occurred invoking 'list_collector_reports': 'pageSize' must be
 *   a string, but a number was provided.
 *
 * That text is the tool's complaint, not an internal error: it names the tool
 * and says what was wrong with the call. It is safe to show (no hostnames, no
 * stack) and it is the only thing that tells the reader — or the client's MCP
 * author — what to fix. Anything else keeps the generic line.
 */
export function extractToolInvocationFailure(
  message: string,
): { toolName: string; errorText: string } | null {
  const match = /An error occurred invoking '([^']+)':\s*([\s\S]+)/.exec(message);
  const toolName = match?.[1]?.trim();
  const detail = match?.[2]?.trim();
  if (!toolName || !detail) return null;
  return { toolName, errorText: sanitizeUpstreamMessage(detail) };
}

/**
 * An upstream message, stripped of anything that looks like a URL. Line
 * breaks survive (a validation list or a traceback reads line by line) and
 * the cap is generous: the chat shows the whole thing, folded when long
 * (DIG-4459). The cap only stops a runaway payload.
 */
export function sanitizeUpstreamMessage(message: string): string {
  return message
    .replace(/https?:\/\/\S+/gi, "[link]")
    .replace(/[^\S\n]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .slice(0, 8000);
}

function numberOf(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

/**
 * The token usage the Responses API reports on `response.completed`.
 *
 * The Responses API counts input/output tokens (not prompt/completion), and
 * names the model that served the turn — which is what the context meter
 * needs to know the window the turn was measured against.
 */
export function extractFoundryUsage(event: unknown): {
  usage: FoundryUsage;
  model?: string;
} | null {
  const response = (event as { response?: Record<string, unknown> })?.response;
  const raw = response?.usage as Record<string, unknown> | undefined;
  if (!raw) return null;
  const input = numberOf(raw.input_tokens ?? raw.prompt_tokens);
  const output = numberOf(raw.output_tokens ?? raw.completion_tokens);
  if (input === undefined && output === undefined) return null;
  const total = numberOf(raw.total_tokens) ?? (input ?? 0) + (output ?? 0);
  const model = typeof response?.model === "string" ? response.model : undefined;
  return {
    usage: { inputTokens: input ?? 0, outputTokens: output ?? 0, totalTokens: total },
    ...(model ? { model } : {}),
  };
}

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
    /** mcp_call: tool name, e.g. `datatap__list_connections`. */
    name?: string;
    /** mcp_call: MCP server label the tool belongs to. */
    server_label?: string;
    /** Provider call correlation id, shared by a call item and its output. */
    call_id?: string;
    /** Output item id; `response.mcp_call_arguments.*` events name it as `item_id`. */
    id?: string;
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
 * MCP `output` is a JSON string of the tool result. Return the parsed value
 * (record, array, or number) so structured results stay structured; fall back
 * to the raw string when it is not JSON. Never throw, never return empty.
 */
function parseMcpResult(value: unknown): Record<string, unknown> | unknown[] | number | string | undefined {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      // JSON `null` parses to a value, but it is not a result. Returning the
      // raw string here would render the literal text `null` as the output.
      if (parsed === null) return undefined;
      if (parsed && typeof parsed === "object") return parsed as Record<string, unknown> | unknown[];
      if (typeof parsed === "number" && Number.isFinite(parsed)) return parsed;
    } catch {
      // Not JSON — fall through to the raw string below.
    }
    return trimmed;
  }
  return undefined;
}

/** Tool identity for an MCP item: tool name, else server label, else "mcp". */
function mcpToolName(item: { name?: string; server_label?: string }): string {
  if (typeof item.name === "string" && item.name.trim()) return item.name.trim();
  if (typeof item.server_label === "string" && item.server_label.trim()) {
    return item.server_label.trim();
  }
  return "mcp";
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
 * assistant answer: `(remote` + `_functions` + `.azure` + `_ai` + `_search` + `)`,
 * `remote_functions.azure_ai_search({...})`, or `(remote search in progress)`.
 * Buffer those fragments and drop the completed token so visitors never see
 * raw tool-call syntax as a reply. An ambiguous prefix such as `(remote` is
 * still flushed at stream end, so a real sentence is not eaten.
 */
export class FoundryToolLeakFilter {
  private buf = "";
  /** Resume point for an open call. The bytes before it are not scanned again. */
  private hold: CallHold | null = null;

  /**
   * @returns text that is safe to stream, or `null` when the delta was held /
   * discarded as tool-leak noise.
   */
  push(delta: string): string | null {
    const cleaned = stripFoundryCitationMarkers(delta);
    if (!cleaned && !this.buf) return null;

    const held = this.hold;
    const drained = held
      ? continueHeldCall(this.buf, held, cleaned)
      : drainLeaks(this.buf + cleaned);
    if (drained.hold.length > MAX_LEAK_HOLD) {
      this.buf = "";
      this.hold = null;
      return (drained.emit + drained.hold) || null;
    }
    this.buf = drained.hold;
    this.hold = drained.holdState;
    return drained.emit || null;
  }

  /**
   * Drains whatever `push` is still holding, for when the stream ends with no
   * further delta to disambiguate it. Without this, a legitimate reply whose
   * final delta happens to look like an in-progress leak token (ends on
   * exactly `(remote` or `remote_functions.azure`, say) was silently dropped:
   * `push` only ever resolves a held prefix by flushing it AHEAD OF a later
   * delta, and a stream that ends here never sends one.
   *
   * A completed tool call, an open `remote_functions.…(` argument list, and
   * `(remote search…` past the ambiguous `(remote` prefix are not flushed:
   * those are the leak, and the stream ended on them.
   *
   * @returns the held text, or `null` if nothing was buffered or it was a leak.
   */
  flush(): string | null {
    if (!this.buf) return null;
    const held = this.buf;
    this.buf = "";
    this.hold = null;
    const drained = drainLeaks(held);
    if (!drained.hold) return drained.emit || null;
    if (abandonedToolLeak(drained.hold)) return drained.emit || null;
    return drained.emit + drained.hold || null;
  }
}

const REMOTE_SEARCH_STATUS = "(remote search in progress)";
/** Past this, an unclosed call is released as prose so it cannot eat the answer. */
const MAX_LEAK_HOLD = 8 * 1024;
const CALL_HEAD = "remote_functions";

interface CallHold {
  i: number;
  wrapped: boolean;
  depth: number;
  quote: string | null;
  /** 1 matching the head, 2 after the head, 3 inside the argument list, 4 wrapper close. */
  phase: 1 | 2 | 3 | 4;
  headI: number;
}

interface Drain {
  emit: string;
  hold: string;
  holdState: CallHold | null;
}

/**
 * A drop that does not advance must not discard the text still in the buffer.
 * `rest === null` means the caller emits `emit` and stops.
 */
export function consumeLeakDrop(
  emit: string,
  rest: string,
  start: number,
  end: number,
): { emit: string; rest: string | null } {
  if (end <= start) return { emit: emit + rest, rest: null };
  return { emit: emit + rest.slice(0, start), rest: rest.slice(end) };
}

/**
 * Emit text with every raw `remote_functions` call removed. A call is
 * recognized at a word boundary anywhere in the buffer, not only at the
 * start. After one call is dropped, the remainder is scanned again, so
 * back-to-back calls go too. An unfinished call, including a trailing
 * `r` / `re` / `rem` / `remo` / `remot`, is held from its start.
 */
function drainLeaks(raw: string): Drain {
  let emit = "";
  let rest = raw;
  while (rest) {
    const leak = findRemoteFunctionsLeak(rest);
    if (leak?.kind === "drop") {
      const step = consumeLeakDrop(emit, rest, leak.start, leak.end);
      if (step.rest === null) return { emit: step.emit, hold: "", holdState: null };
      emit = step.emit;
      rest = step.rest;
      continue;
    }
    if (leak?.kind === "hold") {
      emit += rest.slice(0, leak.start);
      return { emit, hold: rest.slice(leak.start), holdState: leak.hold };
    }
    const status = takeLeadingStatus(rest);
    if (status?.kind === "drop") {
      emit += status.keep;
      rest = status.rest;
      continue;
    }
    if (status?.kind === "hold") return { emit, hold: rest, holdState: null };
    return { emit: emit + rest, hold: "", holdState: null };
  }
  return { emit, hold: "", holdState: null };
}

/** Append to a held call without rereading the bytes already scanned. */
function continueHeldCall(buf: string, hold: CallHold, delta: string): Drain {
  const combined = buf + delta;
  if (combined.length > MAX_LEAK_HOLD) return { emit: combined, hold: "", holdState: null };
  const call = scanRemoteFunctionsCall(combined, hold);
  if (call?.kind === "prefix") return { emit: "", hold: combined, holdState: call.hold };
  if (call?.kind === "complete") return drainLeaks(combined.slice(call.end));
  return drainLeaks(combined);
}

/** `(remote search in progress)` only when it leads the remaining text. */
function takeLeadingStatus(
  text: string,
): { kind: "drop"; keep: string; rest: string } | { kind: "hold" } | null {
  let i = 0;
  while (i < text.length && /\s/.test(text[i]!)) i++;
  const body = text.slice(i);
  const trimmed = body.trimEnd();
  if (!trimmed) return null;
  if (trimmed.startsWith(REMOTE_SEARCH_STATUS)) {
    const after = trimmed.slice(REMOTE_SEARCH_STATUS.length) + body.slice(trimmed.length);
    return { kind: "drop", keep: text.slice(0, i), rest: after };
  }
  if (REMOTE_SEARCH_STATUS.startsWith(trimmed)) return { kind: "hold" };
  return null;
}

/**
 * The first `remote_functions` call at a word boundary. `(` immediately
 * before the name is part of the call. A name glued to another word is not.
 */
function findRemoteFunctionsLeak(
  text: string,
):
  | { kind: "drop"; start: number; end: number }
  | { kind: "hold"; start: number; hold: CallHold }
  | null {
  const needle = "remote";
  let from = 0;
  while (from < text.length) {
    const i = text.indexOf(needle, from);
    if (i < 0) break;
    const prev = i === 0 ? "" : text[i - 1]!;
    if (prev && /[\w]/.test(prev)) {
      from = i + needle.length;
      continue;
    }
    const start = prev === "(" ? i - 1 : i;
    const call = scanRemoteFunctionsCall(text.slice(start));
    if (call?.kind === "complete") return { kind: "drop", start, end: start + call.end };
    if (call?.kind === "prefix") return { kind: "hold", start, hold: call.hold };
    from = i + needle.length;
  }
  return trailingCallPrefix(text);
}

/**
 * A chunk can end inside the word `remote`, before `indexOf("remote")` can
 * see it. Hold that trailing prefix — `r` through `remot`, `(`, or `(r`
 * through `(remote` — using the same `head.startsWith` rule as the call
 * scanner. A trailing `(` is held so the next chunk can finish the call.
 * A letter glued to the previous word is not a boundary.
 */
function trailingCallPrefix(text: string): { kind: "hold"; start: number; hold: CallHold } | null {
  const limit = CALL_HEAD.length + 2;
  const from = Math.max(0, text.length - (limit - 1));
  for (let start = from; start < text.length; start++) {
    const prev = start === 0 ? "" : text[start - 1]!;
    if (prev && /[\w]/.test(prev)) continue;
    const call = scanRemoteFunctionsCall(text.slice(start));
    if (call?.kind === "prefix") return { kind: "hold", start, hold: call.hold };
  }
  return null;
}

/** True when a held prefix is already the leak and will not become a sentence. */
function abandonedToolLeak(raw: string): boolean {
  const t = raw.trim();
  if (REMOTE_SEARCH_STATUS.startsWith(t) && t.length > "(remote".length) return true;
  return /^\(?remote_functions(?:\.[\w]+)+\(/.test(t);
}

/**
 * `remote_functions.<name>` with an optional wrapper and an optional
 * argument list. A prefix is held. A finished call is dropped. Text that
 * is not this shape returns null so the caller can pass it through.
 */
function scanRemoteFunctionsCall(
  t: string,
  held?: CallHold,
): { kind: "prefix"; hold: CallHold } | { kind: "complete"; end: number } | null {
  let i = held?.i ?? 0;
  let wrapped = held?.wrapped ?? false;
  let depth = held?.depth ?? 0;
  let quote: string | null = held?.quote ?? null;
  let phase: 0 | 1 | 2 | 3 | 4 = held?.phase ?? 0;
  let headI = held?.headI ?? 0;
  const prefix = (): { kind: "prefix"; hold: CallHold } => ({
    kind: "prefix",
    hold: { i, wrapped, depth, quote, phase: phase === 0 ? 1 : phase, headI },
  });

  if (phase === 0) {
    if (i >= t.length) return null;
    if (t[i] === "(") {
      wrapped = true;
      i++;
    }
    phase = 1;
    headI = 0;
  }
  if (phase === 1) {
    while (headI < CALL_HEAD.length) {
      if (i >= t.length) return headI > 0 || wrapped ? prefix() : null;
      if (t[i] !== CALL_HEAD[headI]) return null;
      i++;
      headI++;
    }
    phase = 2;
  }
  if (phase === 2) {
    while (i < t.length && t[i] === ".") {
      const dot = i;
      const seg = i + 1;
      i++;
      while (i < t.length && /[\w]/.test(t[i]!)) i++;
      if (i === seg) {
        // Keep the dot for the next chunk so `remote_functions.` + `azure` stays one name.
        if (i >= t.length) {
          i = dot;
          return prefix();
        }
        return null;
      }
    }
    if (i >= t.length) return prefix();
    if (t[i] === ")") {
      // Bare token `(remote_functions.azure_ai_search)` or the same token
      // closed with only a paren. Text after it is the answer.
      const end = i + 1;
      if (wrapped || end === t.length || /\s/.test(t[end] ?? "")) return { kind: "complete", end };
      return null;
    }
    if (t[i] !== "(") return null;
    i++;
    depth = 1;
    quote = null;
    phase = 3;
  }
  if (phase === 3) {
    while (i < t.length && depth > 0) {
      const c = t[i]!;
      if (quote) {
        if (c === "\\") {
          if (i + 1 >= t.length) return prefix();
          i += 2;
          continue;
        }
        if (c === quote) quote = null;
        i++;
        continue;
      }
      if (c === '"' || c === "'") {
        quote = c;
        i++;
        continue;
      }
      if (c === "(" || c === "{" || c === "[") depth++;
      else if (c === ")" || c === "}" || c === "]") depth--;
      i++;
    }
    if (depth > 0 || quote) return i >= t.length ? prefix() : null;
    phase = 4;
  }
  if (wrapped) {
    if (i >= t.length) return prefix();
    // An unclosed wrapper still hides the call. Only a real ")" is consumed.
    if (t[i] === ")") i++;
  }
  return { kind: "complete", end: i };
}

/** Provider call correlation id shared by a call item and its output item. */
function callIdOf(item: { call_id?: string }): string | undefined {
  return typeof item.call_id === "string" && item.call_id.trim() ? item.call_id.trim() : undefined;
}

/** The MCP server's error, as text the chat can show. */
function mcpErrorText(error: unknown): string | undefined {
  if (typeof error === "string") return error.trim() ? sanitizeUpstreamMessage(error) : undefined;
  if (error && typeof error === "object") {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return sanitizeUpstreamMessage(message);
    try {
      return sanitizeUpstreamMessage(JSON.stringify(error, null, 2));
    } catch {
      return undefined;
    }
  }
  return undefined;
}

/**
 * Per-turn mapping state. Foundry emits a call's output as its own item, and
 * the message item carrying citation annotations is the turn's LAST event — a
 * stateless mapper cannot tell "those chunks already reached the wire" from
 * "these annotations are the only source of them".
 */
export interface FoundryMapState {
  /** Set once an `azure_ai_search_call_output` item has streamed this turn. */
  sawSearchOutput: boolean;
  /**
   * MCP call arguments streamed on `response.mcp_call_arguments.delta` /
   * `.done`, keyed by output item id (the events' `item_id`). Foundry can
   * stream an MCP call's input there and close the `mcp_call` item with
   * `arguments` empty or `"{}"`, which left the row showing `{}` (the get_item
   * display bug). The item's `.done` falls back to these and then drops them.
   */
  mcpArguments?: Map<string, StreamedMcpArguments>;
}

interface StreamedMcpArguments {
  text: string;
  /** Set by `.done`: a later delta for the same id starts a new buffer. */
  closed: boolean;
}

/** Cap on one call's streamed arguments; the wire keeps far less anyway. */
const MAX_STREAMED_MCP_ARGUMENTS = 64 * 1024;

function hasKeys(value: Record<string, unknown> | null): value is Record<string, unknown> {
  return value !== null && Object.keys(value).length > 0;
}

function recordMcpArgumentsDelta(state: FoundryMapState, itemId: string, delta: string): void {
  const map = (state.mcpArguments ??= new Map());
  const prior = map.get(itemId);
  const entry = prior && !prior.closed ? prior : { text: "", closed: false };
  if (entry.text.length + delta.length <= MAX_STREAMED_MCP_ARGUMENTS) entry.text += delta;
  map.set(itemId, entry);
}

function recordMcpArgumentsDone(state: FoundryMapState, itemId: string, args: string): void {
  const map = (state.mcpArguments ??= new Map());
  const prior = map.get(itemId);
  // A full `.done` replaces the fragments. An empty or `"{}"` one (the same
  // shape that empties the item) must not throw away fragments that hold the
  // real input.
  if (hasKeys(parseJsonObject(args)) || !prior) {
    map.set(itemId, { text: args.slice(0, MAX_STREAMED_MCP_ARGUMENTS), closed: true });
  } else {
    prior.closed = true;
  }
}

/** Take (and forget) the arguments streamed for one MCP call item. */
function takeStreamedMcpArguments(
  state: FoundryMapState | undefined,
  itemId: string | undefined,
): Record<string, unknown> | null {
  if (!state?.mcpArguments || !itemId) return null;
  const entry = state.mcpArguments.get(itemId);
  state.mcpArguments.delete(itemId);
  return entry ? parseJsonObject(entry.text) : null;
}

function mapOutputItemDone(
  event: OutputItemDoneEvent,
  state?: FoundryMapState,
): FoundryServerEvent | null {
  const item = event.item;

  // The tool this agent actually calls. `arguments` is the model's own search
  // query — the tool INPUT a reader wants to see, and the only honest label
  // for what is happening while it runs.
  if (item?.type === "azure_ai_search_call") {
    const query = parseJsonObject(item.arguments)?.query;
    const q = typeof query === "string" && query.trim() ? query.trim() : undefined;
    const callId = callIdOf(item);
    return {
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: SEARCH_TOOL,
        status: item.status === "failed" ? "failed" : "completed",
        ...(q ? { query: q } : {}),
        ...(callId ? { callId } : {}),
        label: q ? `Searched for: "${q}"` : SEARCH_LABEL,
      },
    };
  }

  // The tool OUTPUT: the chunks the search returned.
  if (item?.type === "azure_ai_search_call_output") {
    const documents = searchOutputDocuments(item.output);
    const callId = callIdOf(item);
    return {
      type: "activity",
      span: {
        operation: "retrieve",
        toolName: SEARCH_TOOL,
        status: item.status === "failed" ? "failed" : "completed",
        label: "Sources",
        ...(documents.length ? { documents } : {}),
        ...(callId ? { callId } : {}),
      },
    };
  }

  // Generic MCP tool call (`mcp_call`, #3861). `arguments` is a JSON string of
  // the tool input; the result arrives on the same item's `output` at `.done`
  // (Responses API has no separate MCP output item — output rides the
  // completed `mcp_call`). Args + JSON result render through the standard
  // tool parts, exactly like a directly-plugged tool.
  // `mcp_approval_request` is intentionally unmapped: trial agents
  // auto-approve server-side (first-party agent, tenant-owned data).
  if (item?.type === "mcp_call") {
    const name = mcpToolName(item);
    const ownArgs = parseJsonObject(item.arguments);
    const streamedArgs = takeStreamedMcpArguments(state, item.id);
    const args = hasKeys(ownArgs) ? ownArgs : (streamedArgs ?? ownArgs);
    // A failed MCP call carries the server's complaint on `error` (string or
    // object) and usually no output. Pass it through as the tool's result so
    // the failed row shows the MCP's own words under the arguments
    // (DIG-4459), instead of the bare "Tool failed.".
    const mcpError = mcpErrorText((item as { error?: unknown }).error);
    const output =
      parseMcpResult(item.output) ??
      (item.status === "failed" && mcpError ? { error: mcpError } : undefined);
    const callId = callIdOf(item);
    return {
      type: "activity",
      span: {
        operation: "execute_tool",
        toolName: name,
        status: item.status === "failed" ? "failed" : "completed",
        ...(args && Object.keys(args).length ? { toolInput: args } : {}),
        ...(output !== undefined ? { toolResult: output } : {}),
        ...(callId ? { callId } : {}),
        label: name,
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
      // The message item is the turn's LAST event. When the search output item
      // already streamed these chunks into the search row's result, emitting a
      // second `file_search` row here appended it after the answer; suppress.
      if (state?.sawSearchOutput) return null;
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
export function mapFoundryEvent(
  event: FoundryStreamEvent,
  state?: FoundryMapState,
): FoundryServerEvent | null {
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
        const callId = callIdOf(item);
        return {
          type: "activity",
          span: {
            operation: "execute_tool",
            toolName: SEARCH_TOOL,
            status: "started",
            ...(callId ? { callId } : {}),
            label: SEARCH_LABEL,
          },
        };
      }
      // MCP call opened early so the row reads "running" while the tool
      // executes; `.done` settles it into the same row via the call-id
      // correlation (same contract as the search branch above).
      if (item?.type === "mcp_call") {
        const name = mcpToolName(item);
        const callId = callIdOf(item);
        return {
          type: "activity",
          span: {
            operation: "execute_tool",
            toolName: name,
            status: "started",
            ...(callId ? { callId } : {}),
            label: name,
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
    // An MCP call's input can stream separately from its item. Collect it so
    // the item's `.done` can show it when the item itself carries none.
    case "response.mcp_call_arguments.delta": {
      const { item_id: itemId, delta } = event as { item_id?: unknown; delta?: unknown };
      if (state && typeof itemId === "string" && typeof delta === "string") {
        recordMcpArgumentsDelta(state, itemId, delta);
      }
      return null;
    }
    case "response.mcp_call_arguments.done": {
      const { item_id: itemId, arguments: args } = event as {
        item_id?: unknown;
        arguments?: unknown;
      };
      if (state && typeof itemId === "string" && typeof args === "string") {
        recordMcpArgumentsDone(state, itemId, args);
      }
      return null;
    }
    case "response.output_item.done": {
      const doneEvent = event as OutputItemDoneEvent;
      const mapped = mapOutputItemDone(doneEvent, state);
      if (state && doneEvent.item?.type === "azure_ai_search_call_output") {
        state.sawSearchOutput = true;
      }
      return mapped;
    }
    case "response.completed": {
      const reported = extractFoundryUsage(event);
      return reported
        ? { type: "done", usage: reported.usage, model: reported.model }
        : { type: "done" };
    }
    case "response.error": {
      const message = String((event as { message?: unknown }).message ?? "Unknown error");
      return isRateLimitFailure(event) ? { type: "rate-limit", message } : { type: "error", message };
    }
    // A throttled model call after the response has started (after tool calls,
    // typically) does not throw at `responses.create`: Foundry fails the
    // response in-stream. Only the rate-limit case is mapped here; any other
    // `response.failed` / `error` keeps its previous handling.
    case "response.failed":
    case "error": {
      if (!isRateLimitFailure(event)) return null;
      return { type: "rate-limit", message: upstreamErrorMessage(event) ?? "rate limit exceeded" };
    }
    default:
      return null;
  }
}

/**
 * Retry schedule for a throttled deployment (429). Cumulative wait is ~59s, which
 * is well inside a demo's patience and far short of a hung request.
 */
const DEFAULT_CAPACITY_RETRY_DELAYS_MS = [2_000, 4_000, 8_000, 15_000, 15_000, 15_000];
const CAPACITY_RETRY_AFTER_CAP_MS = 30_000;

function httpStatusOf(err: unknown): number | undefined {
  if (typeof err !== "object" || err === null) return undefined;
  const candidate = err as { status?: unknown; statusCode?: unknown };
  const raw = typeof candidate.status === "number" ? candidate.status : candidate.statusCode;
  return typeof raw === "number" ? raw : undefined;
}

function retryAfterMs(err: unknown): number | null {
  if (typeof err !== "object" || err === null) return null;
  const headers = (err as { headers?: { get?: (name: string) => string | null } }).headers;
  // Azure sends millisecond variants alongside the standard header; prefer the
  // finer-grained one when both are present.
  for (const name of ["retry-after-ms", "x-ms-retry-after-ms"]) {
    const rawMs = headers?.get?.(name);
    // Headers.get returns null when absent, and Number(null) is 0 — which would
    // start every retry immediately and make the schedule dead code.
    if (rawMs == null || rawMs.trim() === "") continue;
    const ms = Number(rawMs);
    if (Number.isFinite(ms) && ms >= 0) {
      return Math.min(ms, CAPACITY_RETRY_AFTER_CAP_MS);
    }
  }
  const raw = headers?.get?.("retry-after");
  if (raw == null || raw.trim() === "") return null;
  const seconds = Number(raw);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.min(seconds * 1000, CAPACITY_RETRY_AFTER_CAP_MS);
  }
  const asDate = Date.parse(raw);
  if (Number.isNaN(asDate)) return null;
  return Math.min(Math.max(asDate - Date.now(), 0), CAPACITY_RETRY_AFTER_CAP_MS);
}

/**
 * Delay before retrying a capacity failure, or null when it is not retryable.
 *
 * 429 only. A 503 can arrive after Foundry has already committed the user item,
 * and `responses.create` carries the input — retrying it there would append the
 * user turn twice. Throttling happens before processing, so 429 is safe.
 */
export function capacityRetryDelayMs(
  err: unknown,
  attempt: number,
  schedule: readonly number[],
): number | null {
  if (httpStatusOf(err) !== 429) return null;
  const code = (err as { code?: unknown } | null)?.code;
  // A hard quota/billing stop is not transient: retrying only burns the budget.
  if (code === "insufficient_quota" || code === "billing_hard_limit_reached") return null;
  if (attempt >= schedule.length) return null;
  return retryAfterMs(err) ?? schedule[attempt];
}

/**
 * Mid-stream rate-limit resume schedule (DC-18). A turn that fails in-stream
 * has already spent the minute's token budget (a big tool result re-sent on
 * every model step), so short waits only fail again: wait about a window.
 */
const DEFAULT_RATE_LIMIT_RESUME_DELAYS_MS = [30_000, 60_000, 60_000];
const RATE_LIMIT_WAIT_CAP_MS = 90_000;

const RATE_LIMIT_CODES = new Set(["rate_limit_exceeded", "too_many_requests", "429"]);
const HARD_QUOTA_CODES = new Set(["insufficient_quota", "billing_hard_limit_reached"]);
const RATE_LIMIT_TEXT = /exceeded (?:the )?(?:token )?rate limit|rate limit (?:is |has been )?(?:exceeded|reached)|too many requests/i;

/** The upstream error object, wherever this payload keeps it. */
function upstreamErrorObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null) return null;
  const v = value as Record<string, unknown>;
  const response = v.response as Record<string, unknown> | undefined;
  for (const candidate of [response?.error, v.error]) {
    if (typeof candidate === "object" && candidate !== null) return candidate as Record<string, unknown>;
  }
  return v;
}

function upstreamErrorMessage(value: unknown): string | undefined {
  const obj = upstreamErrorObject(value);
  const message = obj?.message ?? (value as { message?: unknown } | null)?.message;
  return typeof message === "string" && message.length > 0 ? message : undefined;
}

function upstreamErrorCode(value: unknown): string | undefined {
  const obj = upstreamErrorObject(value);
  const code = obj?.code ?? (value as { code?: unknown } | null)?.code;
  return typeof code === "string" || typeof code === "number" ? String(code) : undefined;
}

/**
 * True for the model deployment's per-minute limit, however it arrives: a 429
 * from `responses.create`, an SDK `APIError` thrown while iterating the stream
 * (no HTTP status, `code: "rate_limit_exceeded"`), or a `response.failed` /
 * `error` event carrying the same code. A hard quota or billing stop is not a
 * rate limit: waiting will not clear it.
 */
export function isRateLimitFailure(value: unknown): boolean {
  if (value instanceof FoundryRateLimitError) return true;
  const code = upstreamErrorCode(value);
  if (code && HARD_QUOTA_CODES.has(code)) return false;
  if (code && RATE_LIMIT_CODES.has(code)) return true;
  if (httpStatusOf(value) === 429) return true;
  const message = upstreamErrorMessage(value);
  return !!message && RATE_LIMIT_TEXT.test(message);
}

/**
 * The wait the upstream asked for: Retry-After / retry-after-ms headers first,
 * then the "try again in N seconds" / "retry after N seconds" text Azure puts
 * in the message. Null when the upstream named none.
 */
export function rateLimitHintMs(value: unknown): number | null {
  const fromHeaders = retryAfterMs(value);
  if (fromHeaders !== null) return fromHeaders;
  const message = upstreamErrorMessage(value) ?? (value instanceof Error ? value.message : undefined);
  if (!message) return null;
  const match = /(?:try again|retry)\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*(ms|milliseconds?|s|secs?|seconds?)\b/i.exec(message);
  if (!match) return null;
  const n = Number(match[1]);
  if (!Number.isFinite(n) || n < 0) return null;
  return /^m/i.test(match[2]) ? n : n * 1000;
}

/**
 * Delay before resuming a turn that hit the rate limit mid-stream, or null when
 * the schedule is spent. An upstream hint wins (plus a 1s margin, capped);
 * otherwise the schedule, which already approximates a reset window.
 */
export function rateLimitResumeDelayMs(
  value: unknown,
  attempt: number,
  schedule: readonly number[],
): number | null {
  if (!isRateLimitFailure(value)) return null;
  if (attempt >= schedule.length) return null;
  const hint = rateLimitHintMs(value);
  return hint !== null ? Math.min(hint + 1_000, RATE_LIMIT_WAIT_CAP_MS) : schedule[attempt];
}

/** An in-stream rate-limit failure, carried out of the event loop. */
class FoundryRateLimitError extends Error {
  readonly code = "rate_limit_exceeded";
}

/** Shown when the retries are spent; replaces the generic outage line. */
export const RATE_LIMIT_EXHAUSTED_TEXT =
  "The model's per-minute token limit was reached and did not clear after several retries. " +
  "Your question and any results gathered so far are saved in this conversation: " +
  "wait a minute, then send \"continue\" to pick up where it stopped.";

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
  /**
   * Retry schedule for 429/503 on the model call (#5979). Overridable so tests
   * do not spend the real backoff.
   */
  capacityRetryDelaysMs?: readonly number[];
  /**
   * Waits before resuming a turn whose response failed mid-stream on the
   * deployment's rate limit (DC-18). One entry per resume; overridable so
   * tests do not spend the real minute.
   */
  rateLimitResumeDelaysMs?: readonly number[];
  /**
   * Per-turn tool-call cap from `backend.maxToolCalls`. Omit for no cap.
   * Sent as Responses `max_tool_calls` and enforced here for MCP calls.
   */
  maxToolCalls?: number;
  /**
   * The chat's /effort choice, sent as Responses `reasoning.effort`. Omit to
   * keep the model's default level. If Foundry answers 400 with any error that
   * mentions reasoning, or with the agent reference's refusal of overrides, the
   * turn retries once without it and keeps the default for the rest of the turn.
   */
  reasoningEffort?: FoundryReasoningEffort;
  /**
   * Shared guardrails (TPM and the tool cap). Foundry still aborts the
   * response and sends `max_tool_calls` / `tool_choice`; the guard decides
   * when to pause, nudge, or stop.
   */
  guard?: TurnGuard;
}): Promise<Response> {
  const turnMode: DigiTurnMode = opts.turnMode ?? "send";
  const toolCap = normalizeMaxToolCalls(opts.maxToolCalls ?? opts.guard?.toolCap);
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
  // Own message, not part of `message`: edit_last_user persists `message`,
  // and the tool query is the typed text. The instruction rides beside it.
  const privateInstruction = privateModeInstructionText(opts.messages);

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

      // Set when the turn dies because a tool refused the call; the failed
      // row and the turn error both carry the tool's own complaint.
      let failure: { toolName: string; errorText: string } | null = null;

      try {
        let conversationId = opts.conversationId;
        // The no-invent guard (DIG-509 leaf 1b) rides the turn that creates the
        // conversation, so it lands once per conversation instead of once per
        // user message. `opts.conversationId` is the id from before this turn,
        // so this is true exactly when the branch below creates one.
        const createdConversation = !conversationId;
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
        const createParams: {
          conversation: string;
          input?: string | ReadonlyArray<{ role: "user"; content: string }>;
          stream: true;
        } = {
          conversation: conversationId,
          stream: true,
        };
        if (turnMode === "send") {
          // Grounding goes here and not into `message` at the top: `message` is
          // reused as `editedUserText` below, so prepending there would write the
          // block into the conversation as a literal user utterance, brackets
          // and all, on edit_last_user. The private instruction is its own
          // input item so the typed text stays the typed text.
          const spoken = createdConversation ? applyGroundingDirective(message) : message;
          createParams.input = privateInstruction
            ? [
                { role: "user", content: privateInstruction },
                { role: "user", content: spoken },
              ]
            : spoken;
        }

        // Set when Foundry refuses max_tool_calls / tool_choice beside
        // agent_reference. Later creates in this turn omit those fields.
        let apiOverrideRefused = false;
        // Set when Foundry refuses reasoning.effort beside agent_reference.
        // Tracked apart from the tool controls so losing one keeps the other.
        let reasoningOverrideRefused = false;
        const responseBody = (toolChoice?: "none"): FoundryResponsesCreateBody => ({
          agent_reference: { name: opts.agentName, type: "agent_reference" },
          ...(!apiOverrideRefused && toolCap !== undefined ? { max_tool_calls: toolCap } : {}),
          ...(!apiOverrideRefused && toolChoice ? { tool_choice: toolChoice } : {}),
          ...(!reasoningOverrideRefused && opts.reasoningEffort
            ? { reasoning: { effort: opts.reasoningEffort } }
            : {}),
        });

        const createWithCapacityRetry = async (
          params: {
            conversation: string;
            input?: string | ReadonlyArray<{ role: "user"; content: string }>;
            stream: true;
          },
          extras?: { toolChoice?: "none"; signal?: AbortSignal },
        ) => {
          const schedule = opts.capacityRetryDelaysMs ?? DEFAULT_CAPACITY_RETRY_DELAYS_MS;
          const signal = extras?.signal ?? opts.signal;
          // The agent reference already refused per-call tool controls. A
          // follow-up that wanted tool_choice none says so in the input.
          let requestParams = params;
          if (apiOverrideRefused && extras?.toolChoice && requestParams.input === undefined) {
            requestParams = { ...requestParams, input: TOOL_CAP_INSTRUCTION };
          }
          for (let attempt = 0; ; attempt += 1) {
            const body = responseBody(extras?.toolChoice);
            const usedOverride = body.max_tool_calls !== undefined || body.tool_choice !== undefined;
            try {
              const created = await openai.responses.create(requestParams, {
                signal,
                // Our schedule owns the retries; the SDK's own retries would
                // multiply them (up to 21 POSTs for one turn).
                maxRetries: 0,
                body,
              });
              if (attempt > 0) {
                // Capacity is back: clear the waiting state before the answer
                // starts, so the indicator does not sit on a stale message
                // while the first tool call runs.
                writer.write({
                  type: "data-connection",
                  id: "foundry-capacity",
                  data: { state: "ready" },
                });
              }
              return created;
            } catch (err) {
              if (body.reasoning && isReasoningOverrideRejected(err)) {
                // Drop only the effort and send the same request again; this is
                // not a capacity retry, so the backoff schedule does not advance.
                reasoningOverrideRefused = true;
                attempt -= 1;
                continue;
              }
              let failure = err;
              if (usedOverride && isAgentOverrideRejected(err)) {
                apiOverrideRefused = true;
                // tool_choice was the way to force a message. If the agent
                // reference rejects it, say so in the follow-up input instead.
                const retryParams = extras?.toolChoice
                  ? { ...requestParams, input: requestParams.input ?? TOOL_CAP_INSTRUCTION }
                  : requestParams;
                requestParams = retryParams;
                try {
                  const created = await openai.responses.create(retryParams, {
                    signal,
                    maxRetries: 0,
                    body: responseBody(),
                  });
                  if (attempt > 0) {
                    writer.write({
                      type: "data-connection",
                      id: "foundry-capacity",
                      data: { state: "ready" },
                    });
                  }
                  return created;
                } catch (retryErr) {
                  failure = retryErr;
                }
              }
              const delay = capacityRetryDelayMs(failure, attempt, schedule);
              if (delay === null) {
                if (attempt > 0) {
                  // Exhausted, or no longer retryable: clear the waiting state
                  // so the persisted turn does not carry a stale countdown.
                  writer.write({
                    type: "data-connection",
                    id: "foundry-capacity",
                    data: { state: "ready" },
                  });
                }
                throw failure;
              }
              writer.write({
                type: "data-connection",
                id: "foundry-capacity",
                data: {
                  state: "warming_up",
                  message: `Waiting for model capacity — retrying in ${Math.max(
                    1,
                    Math.round(delay / 1000),
                  )}s`,
                },
              });
              await abortableSleep(delay, opts.signal);
              if (opts.signal?.aborted) throw failure;
            }
          }
        };

        const textFilter = new FoundryToolLeakFilter();
        const mapState: FoundryMapState = { sawSearchOutput: false };
        const resumeSchedule = opts.rateLimitResumeDelaysMs ?? DEFAULT_RATE_LIMIT_RESUME_DELAYS_MS;
        const toolCalls = new FoundryToolCallCounter();
        let params = createParams;
        let wroteText = false;
        let resumeSeparatorPending = false;
        let hitToolCap = false;

        const pump = async (
          responseStream: AsyncIterable<FoundryStreamEvent>,
          mode: "capped" | "final",
          abortCap: () => void,
        ): Promise<"cap" | "done"> => {
          for await (const event of responseStream) {
            const sight = toolCap !== undefined ? toolCalls.observe(event) : "ignore";
            if (
              mode === "capped" &&
              toolCap !== undefined &&
              sight === "new" &&
              toolCalls.count > toolCap
            ) {
              // The call that would exceed the cap is not rendered. Abort so
              // Foundry stops executing it; MCP calls are not covered by
              // max_tool_calls (built-in tools only).
              hitToolCap = true;
              abortCap();
              return "cap";
            }
            // The follow-up is one answer. A further tool call is dropped
            // instead of starting another round.
            if (mode === "final" && sight === "new") continue;
            const mapped = mapFoundryEvent(event, mapState);
            if (!mapped) continue;
            if (mapped.type === "text-delta") {
              const pushed = textFilter.push(mapped.delta);
              if (!pushed) continue;
              // A resumed turn continues below what was already shown.
              const delta = resumeSeparatorPending ? `\n\n${pushed}` : pushed;
              resumeSeparatorPending = false;
              wroteText = true;
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
              const detailed = sanitized && applyActivityDetail(sanitized, opts.activityDetail);
              const span =
                detailed && opts.guard?.active && detailed.toolResult !== undefined
                  ? {
                      ...detailed,
                      toolResult: opts.guard.capToolPayload(
                        detailed.toolResult,
                      ) as typeof detailed.toolResult,
                    }
                  : detailed;
              if (span) {
                writeStandardActivity(writer, span, activityCtx);
              }
            } else if (mapped.type === "rate-limit") {
              throw new FoundryRateLimitError(mapped.message);
            } else if (mapped.type === "error") {
              throw new FoundryProtocolError(mapped.message);
            } else if (mapped.type === "done") {
              if (mapped.usage) {
                // Real provider-reported token usage (the Responses API counts
                // them on `response.completed`). The client folds it into
                // `metadata.custom.usage`, which is what the context meter
                // reads; nothing is fabricated when the API sends no counts.
                writer.write({
                  type: "message-metadata",
                  messageMetadata: {
                    usage: mapped.usage,
                    ...(mapped.model ? { model: mapped.model } : {}),
                  },
                });
                opts.guard?.recordUsage(mapped.usage);
              }
              return "done";
            }
          }
          return "done";
        };

        const clearForGuard = async (next: {
          conversation: string;
          input?: string | ReadonlyArray<{ role: "user"; content: string }>;
          stream: true;
        }) => {
          if (!opts.guard?.active) return next;
          const pendingText =
            typeof next.input === "string"
              ? next.input
              : (next.input?.map((item) => item.content).join("\n") ?? "");
          const clearance = await opts.guard.beforeRound({
            writer,
            pendingText,
            toolCallsSoFar: toolCalls.count,
            signal: opts.signal,
          });
          if (clearance.action === "proceed") return next;
          // A private turn's input is already a list. The guard's extra
          // instruction is another item, so it does not glue onto the question.
          if (next.input && typeof next.input !== "string") {
            return {
              ...next,
              input: [...next.input, { role: "user" as const, content: clearance.instruction }],
            };
          }
          const input = next.input
            ? `${next.input}\n\n${clearance.instruction}`
            : clearance.instruction;
          return { ...next, input };
        };

        resumeLoop: for (let resume = 0; ; resume += 1) {
          const child = new AbortController();
          const unlink = forwardAbort(opts.signal, child);
          // Create stays outside the resume catch. A 429 here already spent
          // the capacity schedule; resuming it would wait out another minute
          // on top of those retries. Mid-stream failures (the iterator) are
          // the ones DC-18 resumes.
          let responseStream: AsyncIterable<FoundryStreamEvent>;
          try {
            params = await clearForGuard(params);
            responseStream = await createWithCapacityRetry(params, { signal: child.signal });
          } catch (err) {
            unlink();
            throw err;
          }
          try {
            const outcome = await pump(responseStream, "capped", () => child.abort());
            if (outcome === "cap") break resumeLoop;
          } catch (err) {
            if (opts.signal?.aborted) throw err;
            // The cap abort is ours. SDK abort errors do not set `name`, so
            // matching AbortError / APIUserAbortError misses them and the
            // turn becomes the generic outage line. The flag is enough.
            if (hitToolCap) break resumeLoop;
            if (!isRateLimitFailure(err)) throw err;
            const delay = rateLimitResumeDelayMs(err, resume, resumeSchedule);
            if (delay === null) {
              writer.write({ type: "data-connection", id: "foundry-capacity", data: { state: "ready" } });
              throw err;
            }
            console.warn(
              `[foundry] rate limit mid-stream; resuming in ${Math.round(delay / 1000)}s (attempt ${resume + 1}/${resumeSchedule.length})`,
            );
            await waitOutRateLimit(writer, delay, resume + 1, resumeSchedule.length, opts.signal);
            if (opts.signal?.aborted) throw err;
            // Keep any held leak-prefix text from the failed attempt.
            const held = textFilter.flush();
            if (held) {
              openText();
              writer.write({ type: "text-delta", id: textId, delta: held });
              wroteText = true;
            }
            resumeSeparatorPending = wroteText;
            // Foundry keeps the failed response's items (the user message and
            // every completed tool call) in the conversation, so a create with
            // no new input continues the same turn from those tool results,
            // the same shape regenerate uses. Re-sending the input would
            // duplicate the user message.
            params = { conversation: conversationId, stream: true };
            continue;
          } finally {
            unlink();
          }
          break;
        }

        if (hitToolCap && toolCap !== undefined) {
          // Silent, not an error: the turn continues straight into a final
          // answer, with no notice in the UI.
          let finalParams: {
            conversation: string;
            input?: string | ReadonlyArray<{ role: "user"; content: string }>;
            stream: true;
          } = {
            conversation: conversationId,
            stream: true,
          };
          if (opts.guard?.active) {
            finalParams = await clearForGuard(finalParams);
          }
          resumeSeparatorPending = wroteText;
          try {
            // No new visitor text. tool_choice none is the Responses switch
            // that makes the model generate a message instead of another tool
            // call, on the same request body as agent_reference.
            const finalStream = await createWithCapacityRetry(finalParams, { toolChoice: "none" });
            await pump(finalStream, "final", () => {});
          } catch (err) {
            if (opts.signal?.aborted) throw err;
            if (isRateLimitFailure(err)) throw err;
            console.error(
              "[foundry] tool-cap final answer failed",
              err instanceof Error ? err.message : String(err),
            );
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
        failure = isRateLimitFailure(err)
          ? null
          : extractToolInvocationFailure(err instanceof Error ? err.message : String(err));
        if (isRateLimitFailure(err)) {
          // The deployment's per-minute limit, still in force after the
          // retries: say so plainly instead of the generic outage line.
          console.warn("[foundry] rate limit retries exhausted");
          writer.write({ type: "error", errorText: RATE_LIMIT_EXHAUSTED_TEXT });
        } else if (failure) {
          // A tool refused the call: say which tool and why, instead of the
          // generic outage line that hides it.
          writer.write({
            type: "error",
            errorText: `${failure.toolName}: ${failure.errorText}`,
          });
        } else if (err instanceof FoundryProtocolError) {
          writer.write({
            type: "error",
            errorText: `Upstream error: ${err.message}`,
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
            type: "error",
            errorText: "The assistant is unavailable right now. Please try again shortly.",
          });
        }
      } finally {
        opts.guard?.release();
        // Orphaned started rows settle as failed — a row whose tool never
        // returned must not render as a successful completion.
        finishStandardActivity(
          writer,
          activityCtx,
          failure
            ? { toolName: failure.toolName, errorText: failure.errorText }
            : undefined,
        );
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
