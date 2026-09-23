/**
 * Stream plumbing for the hand-rolled protocol adapters (#4543).
 *
 * LangGraph, AG-UI and A2A each publish a client SDK, but the BFF only
 * *consumes* a server-sent event stream and normalizes it onto the shared
 * `ActivitySpan` vocabulary — exactly what the digigraph and foundry adapters
 * already do by hand. Hand-rolling keeps three dependency trees (rxjs, uuid,
 * fast-json-patch, …) out of the image for a fraction of their surface.
 */
import {
  applyActivityDetail,
  sanitizeActivitySpan,
  type ActivityDetail,
  type ActivitySpan,
} from "@/lib/chat-activity";
import {
  closeOpenReasoning,
  writeStandardActivity,
  type StandardActivityContext,
  type UiStreamWriter,
} from "@/lib/ui-stream-parts";

export type SseEvent = { event: string | null; data: string };

/** Read an SSE body into `{ event, data }` blocks. Cancels the reader on exit. */
export async function* iterateSse(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      if (signal?.aborted) {
        throw new DOMException("The operation was aborted.", "AbortError");
      }
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) !== -1) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let event: string | null = null;
        const dataLines: string[] = [];
        for (const rawLine of block.split("\n")) {
          const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
        }
        if (!dataLines.length) continue;
        yield { event, data: dataLines.join("\n") };
      }
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      /* the stream already closed */
    }
  }
}

/** JSON-decode one SSE payload as unknown; null for `[DONE]`, blank or bad JSON. */
export function parseSseValue(data: string): unknown {
  const trimmed = data.trim();
  if (!trimmed || trimmed === "[DONE]") return null;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return null;
  }
}

/** JSON-decode one SSE payload, keeping objects only (LangGraph sends arrays). */
export function parseSseJson(data: string): Record<string, unknown> | null {
  const parsed = parseSseValue(data);
  return isRecord(parsed) ? parsed : null;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function stringField(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

export type TextWriter = {
  open: () => void;
  delta: (text: string) => void;
  close: () => void;
  readonly emitted: boolean;
};

/**
 * Assistant answer text as standard `text-start` / `text-delta` / `text-end`
 * chunks. Opening text ends any reasoning block first, matching the digigraph
 * adapter so a thinking row can never sit above later answer text.
 */
export function createTextWriter(writer: UiStreamWriter, ctx: StandardActivityContext): TextWriter {
  let seq = 0;
  let id = "assistant-main";
  let open = false;
  let emitted = false;
  const openText = () => {
    if (open) return;
    closeOpenReasoning(writer, ctx);
    id = seq === 0 ? "assistant-main" : `assistant-main-${seq}`;
    writer.write({ type: "text-start", id });
    open = true;
  };
  return {
    open: openText,
    delta: (text: string) => {
      if (!text) return;
      openText();
      emitted = true;
      writer.write({ type: "text-delta", id, delta: text });
    },
    close: () => {
      if (!open) return;
      writer.write({ type: "text-end", id });
      open = false;
      seq += 1;
    },
    get emitted() {
      return emitted;
    },
  };
}

/**
 * Sanitize + disclosure-gate a raw span and write it. Every adapter in this
 * family routes through here so the `activityDetail` policy is applied once
 * (the same two calls the digigraph and foundry adapters make inline).
 */
export function writeGatedSpan(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  raw: Record<string, unknown>,
  activityDetail: ActivityDetail,
): ActivitySpan | null {
  const sanitized = sanitizeActivitySpan(raw);
  if (!sanitized) return null;
  const gated = applyActivityDetail(sanitized, activityDetail);
  if (!gated) return null;
  writeStandardActivity(writer, gated, ctx);
  return gated;
}

/** A provider thinking delta as a reasoning span. */
export function writeReasoningDelta(
  writer: UiStreamWriter,
  ctx: StandardActivityContext,
  delta: string,
  activityDetail: ActivityDetail,
): void {
  if (!delta) return;
  writeGatedSpan(
    writer,
    ctx,
    { operation: "chat", status: "started", label: "Thinking", reasoningDelta: delta },
    activityDetail,
  );
}

/** Parse a tool-argument blob that may be a JSON string, an object, or junk. */
export function parseToolInput(raw: unknown): Record<string, unknown> | null {
  if (isRecord(raw)) return raw;
  if (typeof raw !== "string" || !raw.trim()) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isRecord(parsed) ? parsed : { value: parsed };
  } catch {
    return { value: raw };
  }
}
