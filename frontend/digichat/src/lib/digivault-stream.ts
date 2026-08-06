/**
 * Digivault backend adapter — ports the Cloudflare agentic digivault loop into
 * a Node route handler that emits the AI SDK UI message stream (not NDJSON).
 */
import {
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
  type UIMessageStreamWriter,
} from "ai";
import {
  ACTIVITY_PART_TYPE,
  applyActivityDetail,
  sanitizeActivitySpan,
  type ActivityDetail,
  type ActivitySpan,
} from "./chat-activity";
import { resolveDigivaultLlmRoute, QUOTA_MESSAGE, type LlmRoute } from "./digivault-byok";
import type { DigivaultResolvedEnv } from "./digivault-env";
import { mapDigivaultNdjsonEvent } from "./digivault-ndjson-adapter";
import {
  SYSTEM_PROMPT,
  MAX_TOOL_ROUNDS,
  UpstreamError,
  callModel,
  parseToolQuery,
  hasVaultResults,
  type ConvoMessage,
} from "./digivault-llm";
import { searchArchitectureNotes, buildToolContext, TOP_K } from "./digivault-vault";
import { lastUserMessageText } from "./external-relay-stream";

const NO_CONTENT_NOTE =
  "⚠ the model pool returned no content — the free models may be rate-limited or out of daily " +
  "quota. Please retry in a moment.";

const EMPTY_ANSWER_NOTE =
  "⚠ the model thought about your question but didn't finish an answer — it may have failed to " +
  "call digivault. Retry, or add your own API key in settings for more reliable tool use.";

const UNAVAILABLE = "the model is temporarily unavailable — please retry";

type NdjsonLike =
  | { type: "status"; message: string }
  | { type: "tool_call"; name: string; query: string }
  | {
      type: "tool_result";
      name: string;
      query: string;
      hits: Array<{ title: string; path: string }>;
      count: number;
    }
  | { type: "reasoning"; delta: string }
  | { type: "content"; delta: string }
  | { type: "quota_exhausted"; message: string }
  | { type: "error"; message: string }
  | { type: "done" };

function writeActivity(
  writer: UIMessageStreamWriter,
  span: ActivitySpan,
  detail: ActivityDetail,
  seq: { n: number },
): void {
  const sanitized = sanitizeActivitySpan(span);
  const gated = sanitized && applyActivityDetail(sanitized, detail);
  if (!gated) return;
  writer.write({
    type: ACTIVITY_PART_TYPE,
    id: `digivault-activity-${seq.n++}`,
    data: gated,
  });
}

function emitNdjsonAsUi(
  writer: UIMessageStreamWriter,
  event: NdjsonLike,
  detail: ActivityDetail,
  seq: { n: number },
  text: { open: () => void; write: (delta: string) => void },
): void {
  if (event.type === "content") {
    text.open();
    text.write(event.delta);
    return;
  }
  if (event.type === "quota_exhausted") {
    writeActivity(
      writer,
      { operation: "chat", status: "failed", label: event.message || QUOTA_MESSAGE },
      detail,
      seq,
    );
    text.open();
    text.write(event.message || QUOTA_MESSAGE);
    return;
  }
  if (event.type === "error") {
    text.open();
    text.write(event.message);
    return;
  }
  if (event.type === "done") return;

  const mapped = mapDigivaultNdjsonEvent(event);
  if (!mapped) return;
  if (mapped.type === "text-delta") {
    text.open();
    text.write(mapped.delta);
    return;
  }
  if (mapped.type === "activity") {
    writeActivity(writer, mapped.span, detail, seq);
  }
}

async function runVaultTool(
  env: DigivaultResolvedEnv,
  name: string,
  rawArgs: string,
  fetchFn: typeof fetch,
): Promise<{ text: string; hits: Array<{ title: string; path: string }>; query: string }> {
  const query = parseToolQuery(rawArgs);
  if (name !== "search_digivault") {
    return { text: `Unknown tool: ${name}`, hits: [], query };
  }
  if (!query) {
    return { text: "No search query was provided.", hits: [], query: "" };
  }
  try {
    const hits = await searchArchitectureNotes({
      supabaseUrl: env.supabaseUrl,
      supabaseAnonKey: env.supabaseAnonKey,
      query,
      matchCount: TOP_K,
      fetchImpl: fetchFn,
    });
    if (!hits.length) {
      return {
        text: "No matching documentation was found in the digivault for that query.",
        hits: [],
        query,
      };
    }
    const { toolText, activityDocuments } = buildToolContext(hits);
    return {
      text: toolText,
      hits: activityDocuments.map((d) => ({ title: d.title, path: d.path })),
      query,
    };
  } catch (e) {
    console.error("digivault tool failed:", e instanceof Error ? e.message : String(e));
    return {
      text: "The digivault is temporarily unavailable — tell the user to try again shortly.",
      hits: [],
      query,
    };
  }
}

function emitQuotaIfFree(route: LlmRoute, emit: (ev: NdjsonLike) => void): void {
  if (route.kind === "openai_compat" && route.isFreePool) {
    emit({ type: "quota_exhausted", message: QUOTA_MESSAGE });
  }
}

async function runAgenticLoop(opts: {
  convo: ConvoMessage[];
  env: DigivaultResolvedEnv;
  route: LlmRoute;
  emit: (ev: NdjsonLike) => void;
  fetchFn: typeof fetch;
  signal?: AbortSignal;
}): Promise<void> {
  const { env, route, emit, fetchFn, signal } = opts;
  const messages = [...opts.convo];

  for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
    if (signal?.aborted) return;
    emit({
      type: "status",
      message: round === 0 ? "Thinking…" : "Reviewing digivault results…",
    });

    let msg: { content: string; tool_calls: Awaited<ReturnType<typeof callModel>>["tool_calls"] };
    try {
      msg = await callModel(route, messages, fetchFn);
    } catch (e) {
      const err = e as UpstreamError;
      console.error("model call failed:", err.message);
      if (err.quota) {
        emitQuotaIfFree(route, emit);
        emit({ type: "content", delta: NO_CONTENT_NOTE });
        return;
      }
      emit({ type: "error", message: UNAVAILABLE });
      return;
    }

    const toolCalls = msg.tool_calls ?? [];
    if (toolCalls.length > 0) {
      messages.push({ role: "assistant", content: msg.content ?? "", tool_calls: toolCalls });
      for (const tc of toolCalls) {
        const name = tc.function?.name ?? "search_digivault";
        const rawArgs = tc.function?.arguments ?? "";
        const query = parseToolQuery(rawArgs) || "(unspecified)";
        emit({ type: "tool_call", name, query });
        emit({ type: "status", message: "Searching digivault…" });
        const result = await runVaultTool(env, name, rawArgs, fetchFn);
        emit({
          type: "tool_result",
          name,
          query: result.query || query,
          hits: result.hits,
          count: result.hits.length,
        });
        messages.push({ role: "tool", tool_call_id: tc.id, content: result.text });
      }
      continue;
    }

    if (!hasVaultResults(messages) && !(msg.content ?? "").trim() && round === 0) {
      emit({ type: "status", message: "Requesting digivault search…" });
      try {
        const retry = await callModel(route, messages, fetchFn, "search_digivault");
        if (retry.tool_calls.length > 0) {
          messages.push({
            role: "assistant",
            content: retry.content ?? "",
            tool_calls: retry.tool_calls,
          });
          for (const tc of retry.tool_calls) {
            const name = tc.function?.name ?? "search_digivault";
            const rawArgs = tc.function?.arguments ?? "";
            const query = parseToolQuery(rawArgs) || "(unspecified)";
            emit({ type: "tool_call", name, query });
            emit({ type: "status", message: "Searching digivault…" });
            const result = await runVaultTool(env, name, rawArgs, fetchFn);
            emit({
              type: "tool_result",
              name,
              query: result.query || query,
              hits: result.hits,
              count: result.hits.length,
            });
            messages.push({ role: "tool", tool_call_id: tc.id, content: result.text });
          }
          continue;
        }
        if ((retry.content ?? "").trim()) {
          emit({ type: "content", delta: retry.content.trim() });
          return;
        }
      } catch (e) {
        console.error("forced tool retry failed:", e instanceof Error ? e.message : String(e));
      }
    }

    emit({ type: "status", message: "Writing answer…" });
    const prefilled = (msg.content ?? "").trim();
    if (prefilled) {
      emit({ type: "content", delta: prefilled });
      return;
    }

    // No prefilled content and no stream path needed for the Node port when
    // callModel already returned empty — surface the same CF notes.
    emit({
      type: "content",
      delta: hasVaultResults(messages) ? EMPTY_ANSWER_NOTE : NO_CONTENT_NOTE,
    });
    if (!hasVaultResults(messages)) emitQuotaIfFree(route, emit);
    return;
  }

  emit({
    type: "content",
    delta: "⚠ I couldn't finish that within a few steps — please rephrase or try again.",
  });
}

export async function createDigivaultStreamResponse(opts: {
  messages: UIMessage[];
  env: DigivaultResolvedEnv;
  responseHeaders: Record<string, string>;
  activityDetail: ActivityDetail;
  byokKey?: string;
  byokProvider?: string;
  byokModel?: string;
  signal?: AbortSignal;
  /** test seam */
  fetchImpl?: typeof fetch;
}): Promise<Response> {
  const fetchFn = opts.fetchImpl ?? fetch;
  const userText = lastUserMessageText(opts.messages);

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "digivault error"),
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
      const seq = { n: 0 };
      const text = {
        open: openText,
        write: (delta: string) => {
          writer.write({ type: "text-delta", id: textId, delta });
        },
      };

      if (opts.signal?.aborted) return;

      try {
        const route = resolveDigivaultLlmRoute({
          byokKey: opts.byokKey,
          byokProvider: opts.byokProvider,
          byokModel: opts.byokModel,
          openRouterKey: opts.env.openRouterKey,
        });
        if ("error" in route) {
          openText();
          text.write(
            route.status === 400
              ? route.error
              : "The assistant is unavailable right now. Please try again shortly.",
          );
          return;
        }

        const convo: ConvoMessage[] = [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: userText },
        ];

        await runAgenticLoop({
          convo,
          env: opts.env,
          route,
          fetchFn,
          signal: opts.signal,
          emit: (ev) => emitNdjsonAsUi(writer, ev, opts.activityDetail, seq, text),
        });
      } catch (err) {
        if (opts.signal?.aborted) return;
        console.error(
          "[digivault] stream error",
          err instanceof Error ? err.message : String(err),
        );
        openText();
        text.write("The assistant is unavailable right now. Please try again shortly.");
      } finally {
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
