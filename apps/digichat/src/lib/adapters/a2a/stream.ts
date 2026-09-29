/**
 * A2A adapter (#4543).
 *
 * JSON-RPC 2.0 over HTTP: `POST {baseUrl}` with `message/stream`, answered by
 * an SSE stream of `{ jsonrpc, id, result }` envelopes whose `result.kind` is
 * `task`, `status-update` or `artifact-update` (a blocking server answers with
 * a single JSON envelope instead — both shapes are handled).
 *
 * A2A has no reasoning channel: tasks carry status and artifacts only, so
 * `capabilities.reasoning` is false and agent text arrives as artifact /
 * status-message parts.
 */
import { createUIMessageStream, createUIMessageStreamResponse, type UIMessage } from "ai";
import type { ActivityDetail } from "@/lib/chat-activity";
import {
  createActivityWriteContext,
  finishStandardActivity,
  uiMessagesForUpstream,
  type StandardActivityContext,
  type UiStreamWriter,
} from "@/lib/ui-stream-parts";
import { toChatMessages } from "@/lib/adapters/shared/messages";
import {
  createTextWriter,
  isRecord,
  iterateSse,
  parseSseJson,
  stringField,
  writeFailureStatus,
  writeGatedSpan,
  type TextWriter,
} from "@/lib/adapters/shared/stream-utils";
import type { A2aBackendConfig } from "@/lib/backend-adapters";

type Consumer = {
  writer: UiStreamWriter;
  ctx: StandardActivityContext;
  text: TextWriter;
  activityDetail: ActivityDetail;
  /** Text each artifact has already contributed, so resends emit only the tail. */
  artifacts: Map<string, string>;
};

/** Text of an A2A `Part[]` (text parts joined; data/file parts are ignored). */
function partsText(parts: unknown): string {
  if (!Array.isArray(parts)) return "";
  let out = "";
  for (const part of parts) {
    if (!isRecord(part)) continue;
    if (part.kind === "text" && typeof part.text === "string") out += part.text;
  }
  return out;
}

/** Terminal A2A task states that mean the run failed. */
const FAILED_STATES = new Set(["failed", "canceled", "cancelled", "rejected"]);

/**
 * New text for an artifact. A2A `TaskArtifactUpdateEvent` may resend the
 * cumulative artifact (`append: false`) and a `task` snapshot repeats the
 * artifacts it already carried, so only the delta against what this artifact
 * contributed is emitted — otherwise the answer text duplicates.
 */
function artifactDelta(
  artifact: Record<string, unknown>,
  emitted: Map<string, string>,
): string {
  const id = stringField(artifact, "artifactId") ?? "artifact";
  const full = partsText(artifact.parts);
  const previous = emitted.get(id) ?? "";
  if (full === previous) return "";
  emitted.set(id, full);
  return previous && full.startsWith(previous) ? full.slice(previous.length) : full;
}

function consumeResult(result: Record<string, unknown>, c: Consumer): void {
  const kind = stringField(result, "kind");

  if (kind === "message") {
    const text = partsText(result.parts);
    if (text) c.text.delta(text);
    return;
  }

  if (kind === "task") {
    const status = isRecord(result.status) ? result.status : null;
    if (status) {
      const text = partsText(isRecord(status.message) ? status.message.parts : undefined);
      if (text) c.text.delta(text);
    }
    const artifacts = Array.isArray(result.artifacts) ? result.artifacts : [];
    for (const artifact of artifacts) {
      if (!isRecord(artifact)) continue;
      const text = artifactDelta(artifact, c.artifacts);
      if (text) c.text.delta(text);
    }
    return;
  }

  if (kind === "artifact-update") {
    const artifact = isRecord(result.artifact) ? result.artifact : null;
    const text = artifact ? artifactDelta(artifact, c.artifacts) : "";
    if (text) c.text.delta(text);
    return;
  }

  if (kind === "status-update") {
    const status = isRecord(result.status) ? result.status : null;
    const state = status ? stringField(status, "state") : null;
    const message = status && isRecord(status.message) ? partsText(status.message.parts) : "";
    if (message) c.text.delta(message);
    if (state && FAILED_STATES.has(state)) {
      c.text.close();
      writeGatedSpan(
        c.writer,
        c.ctx,
        { operation: "chat", status: "failed", label: `A2A ${state}` },
        c.activityDetail,
      );
    }
    return;
  }
}

export async function createA2aStreamResponse(opts: {
  backend: A2aBackendConfig;
  messages: UIMessage[];
  responseHeaders: Record<string, string>;
  activityDetail: ActivityDetail;
  /** Resolved by the caller from `backend.apiKeyEnv`; null when unset. */
  apiKey: string | null;
  signal?: AbortSignal;
}): Promise<Response> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream, application/json",
  };
  if (opts.apiKey) headers.Authorization = `Bearer ${opts.apiKey}`;
  const body = JSON.stringify({
    jsonrpc: "2.0",
    id: crypto.randomUUID(),
    method: "message/stream",
    params: {
      message: {
        kind: "message",
        messageId: crypto.randomUUID(),
        role: "user",
        parts: toChatMessages(uiMessagesForUpstream(opts.messages)).map((m) => ({
          kind: "text",
          text: `${m.role}: ${m.content}`,
        })),
      },
    },
  });

  const stream = createUIMessageStream({
    onError: (error) => (error instanceof Error ? error.message : "a2a stream error"),
    execute: async ({ writer }) => {
      const ctx = createActivityWriteContext();
      const text = createTextWriter(writer, ctx);
      const artifacts = new Map<string, string>();
      try {
        const res = await fetch(opts.backend.baseUrl, {
          method: "POST",
          headers,
          body,
          signal: opts.signal,
        });
        if (!res.ok) {
          await res.body?.cancel().catch(() => {});
          writeFailureStatus(writer, ctx, `A2A ${res.status}`, opts.activityDetail);
          return;
        }
        const contentType = res.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          // Blocking server: one JSON-RPC envelope, no stream.
          const envelope = (await res.json()) as unknown;
          if (isRecord(envelope)) {
            if (isRecord(envelope.result)) consumeResult(envelope.result, { writer, ctx, text, activityDetail: opts.activityDetail, artifacts });
            else if (isRecord(envelope.error)) {
              writeGatedSpan(
                writer,
                ctx,
                { operation: "chat", status: "failed", label: stringField(envelope.error, "message") ?? "A2A error" },
                opts.activityDetail,
              );
            }
          }
          return;
        }
        if (!res.body) return;
        for await (const evt of iterateSse(res.body, opts.signal)) {
          const envelope = parseSseJson(evt.data);
          if (!envelope) continue;
          if (isRecord(envelope.result)) consumeResult(envelope.result, { writer, ctx, text, activityDetail: opts.activityDetail, artifacts });
          else if (isRecord(envelope.error)) {
            writeGatedSpan(
              writer,
              ctx,
              { operation: "chat", status: "failed", label: stringField(envelope.error, "message") ?? "A2A error" },
              opts.activityDetail,
            );
          }
        }
      } finally {
        text.close();
        finishStandardActivity(writer, ctx);
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
