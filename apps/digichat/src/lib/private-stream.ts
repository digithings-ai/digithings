/**
 * Private session, server side: what leaves `/api/chat` while a private turn
 * streams.
 *
 * The prompt (`private-mode.ts`) asks the model for stand-ins. This module is
 * the part that does not depend on the model:
 *
 * 1. **Work payloads never reach the browser.** Tool arguments, tool results,
 *    tool error text, reasoning text, sources and activity payloads are
 *    removed from the UI message stream. What is left is enough to draw a
 *    step: a tool row's id, a neutral name, and whether it finished or failed;
 *    a reasoning block's start and end. The client cannot open a step because
 *    there is nothing in it, and an export of the stored thread has nothing to
 *    leak.
 * 2. **A deterministic scrub of the answer text.** Email addresses and phone
 *    numbers become consistent placeholders, and the tenant's own names (its
 *    slug and operator MCP server ids) become a generic label. It is a safety
 *    net under the prompt, not anonymisation: names the model repeats are the
 *    prompt's job.
 *
 * Works on the wire format every chat path shares (AI SDK UI message stream:
 * SSE `data: {json}` events), so one wrapper covers every backend adapter.
 */

const encoder = new TextEncoder();

/** Label a tenant's own names are replaced with in visible text. */
export const PRIVATE_TERM_LABEL = "the help desk";

/**
 * Text a private reasoning block carries in place of the model's reasoning.
 * Clients drop an empty reasoning block, so the step would not show at all;
 * this fixed marker keeps the step visible and carries nothing.
 */
export const PRIVATE_REASONING_TEXT = "…";

/** Error text a failed step carries in a private session. */
export const PRIVATE_TOOL_ERROR = "Step failed.";

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
// A phone number: optional +country, optional (area), then 2-4 digit groups
// joined by space, dot or dash; or a bare +international run. Matches are kept
// only with 9+ digits, so dates, times and short ids pass through.
const PHONE_RE = /(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?\d{2,4}(?:[\s.-]\d{2,4}){2,5}|\+\d{9,15}/g;

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The tenant's own names: slug and operator MCP server ids, 3+ chars. */
export function privateTermsFor(cfg: {
  slug?: string | null;
  mcp?: { servers?: ReadonlyArray<{ id?: string | null }> | null } | null;
} | null | undefined): string[] {
  if (!cfg) return [];
  const out = new Set<string>();
  const add = (raw: string | null | undefined) => {
    const term = (raw ?? "").trim();
    if (term.length >= 3 && term !== "embed" && term !== "digithings") out.add(term);
  };
  add(cfg.slug);
  for (const server of cfg.mcp?.servers ?? []) add(server?.id);
  return [...out];
}

/** Stateful scrubber: the same email or phone gets the same placeholder. */
export class PrivateTextScrubber {
  private readonly emails = new Map<string, string>();
  private readonly phones = new Map<string, string>();
  private readonly termRe: RegExp | null;

  constructor(terms: readonly string[] = []) {
    const words = terms.filter(Boolean).map(escapeRegExp);
    // Also catch the term glued to a tool prefix: `helpdesk_search_tickets`.
    this.termRe = words.length
      ? new RegExp(`(?<![A-Za-z0-9])(?:${words.join("|")})(?![A-Za-z0-9])`, "gi")
      : null;
  }

  scrub(text: string): string {
    if (!text) return text;
    let out = text.replace(EMAIL_RE, (hit) => {
      const key = hit.toLowerCase();
      let alias = this.emails.get(key);
      if (!alias) {
        alias = `contact${this.emails.size + 1}@example.com`;
        this.emails.set(key, alias);
      }
      return alias;
    });
    out = out.replace(PHONE_RE, (hit) => {
      const digits = hit.replace(/\D/g, "");
      if (digits.length < 9) return hit;
      let alias = this.phones.get(digits);
      if (!alias) {
        alias = `+1 555 01${String(this.phones.size).padStart(2, "0")}`;
        this.phones.set(digits, alias);
      }
      return alias;
    });
    if (this.termRe) out = out.replace(this.termRe, PRIVATE_TERM_LABEL);
    return out;
  }

  /** A tool name with the tenant's own names removed: `helpdesk_search_tickets` → `search_tickets`. */
  toolName(name: string): string {
    if (!this.termRe || !name) return name;
    const stripped = name
      .replace(this.termRe, "")
      .replace(/^[_\-.\s]+|[_\-.\s]+$/g, "")
      .replace(/[_\-.\s]{2,}/g, "_");
    return stripped || "tool";
  }
}

export type Chunk = Record<string, unknown> & { type?: unknown };

/** Parts whose payload is the work itself and is never sent in a private session. */
const DROP_TYPES = new Set([
  "reasoning-delta",
  "tool-input-delta",
  "source-url",
  "source-document",
]);

/** Data parts that carry no user content and may pass. */
const KEEP_DATA_TYPES = new Set([
  "data-connection",
  "data-notice",
  // The upstream conversation id (opaque). The embed stores it and sends it
  // back as X-External-Conversation, so dropping it would start every
  // private turn in a fresh upstream conversation.
  "data-conversation",
  "data-externalConversation",
]);

/**
 * Rewrite one UI message stream chunk for a private session. Returns `null`
 * to drop it. Text deltas are handled by the stream (they need buffering).
 */
export function privatizeChunk(chunk: Chunk, scrubber: PrivateTextScrubber): Chunk | null {
  const type = typeof chunk.type === "string" ? chunk.type : "";
  if (DROP_TYPES.has(type)) return null;
  switch (type) {
    case "reasoning-start":
    case "reasoning-end":
      return { type, id: chunk.id };
    case "tool-input-start": {
      const toolName = scrubber.toolName(String(chunk.toolName ?? ""));
      return { type, toolCallId: chunk.toolCallId, toolName };
    }
    case "tool-input-available":
      return {
        type,
        toolCallId: chunk.toolCallId,
        toolName: scrubber.toolName(String(chunk.toolName ?? "")),
        input: {},
      };
    case "tool-input-error":
      return {
        type,
        toolCallId: chunk.toolCallId,
        toolName: scrubber.toolName(String(chunk.toolName ?? "")),
        input: {},
        errorText: PRIVATE_TOOL_ERROR,
      };
    case "tool-output-available":
      return { type, toolCallId: chunk.toolCallId, output: {} };
    case "tool-output-error":
      return { type, toolCallId: chunk.toolCallId, errorText: PRIVATE_TOOL_ERROR };
    case "data-status": {
      const data = (chunk.data ?? {}) as Record<string, unknown>;
      const next: Record<string, unknown> = {};
      if (typeof data.status === "string") next.status = data.status;
      if (typeof data.label === "string") next.label = scrubber.scrub(data.label);
      return { ...chunk, data: next };
    }
    default:
      break;
  }
  if (type.startsWith("data-") && !KEEP_DATA_TYPES.has(type)) return null;
  return chunk;
}

/** Held-back text is released past this length, so a long run cannot stall the answer. */
const MAX_HELD_BACK = 256;
// A trailing run that may still grow into a phone number: it starts at a word
// boundary with a digit, `+` or `(`, and holds only digits and phone separators.
const TRAILING_PHONE_RUN_RE = /(?:^|\s)([+(]?\d[\d\s().+-]*)$/;

/**
 * Hold back a delta's last partial word so a split email is scrubbed whole,
 * and a trailing digit run too: a phone number is written with spaces
 * (`+39 06 1234 5678`), so cutting at the last space would let its first
 * groups out before the rest arrives, and neither piece would match.
 */
export function splitAtLastBoundary(text: string): [ready: string, rest: string] {
  const at = Math.max(text.lastIndexOf(" "), text.lastIndexOf("\n"), text.lastIndexOf("\t"));
  if (at === -1) return text.length > MAX_HELD_BACK ? [text, ""] : ["", text];
  let cut = at + 1;
  const run = TRAILING_PHONE_RUN_RE.exec(text.slice(0, cut));
  if (run) cut = run.index + run[0].length - run[1].length;
  if (text.length - cut > MAX_HELD_BACK) cut = at + 1;
  return [text.slice(0, cut), text.slice(cut)];
}

/**
 * SSE transform for a private turn. Parses `data:` events, rewrites them with
 * {@link privatizeChunk}, scrubs answer text (buffered to word boundaries per
 * text part), and passes non-JSON events (`[DONE]`) through.
 */
export function createPrivateStreamTransform(
  terms: readonly string[] = [],
  /** Sees each raw chunk before it is stripped (server-side tool memory). */
  onRawChunk?: (chunk: Chunk) => void,
): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const scrubber = new PrivateTextScrubber(terms);
  const pending = new Map<string, string>();
  // Upstream tool call ids can be short and reused every turn (`tool-1`). The
  // browser and the server-side tool memory get a fresh unguessable id per
  // call instead, so a kept payload can neither be guessed nor overwritten by
  // a later turn's `tool-1`.
  const toolIds = new Map<string, string>();
  const aliasToolCallId = (id: string): string => {
    let alias = toolIds.get(id);
    if (!alias) {
      alias = `ptc_${crypto.randomUUID()}`;
      toolIds.set(id, alias);
    }
    return alias;
  };
  let buffer = "";

  const emit = (controller: TransformStreamDefaultController<Uint8Array>, chunk: unknown) => {
    controller.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`));
  };

  const flushText = (controller: TransformStreamDefaultController<Uint8Array>, id: string) => {
    const rest = pending.get(id);
    pending.delete(id);
    if (rest) emit(controller, { type: "text-delta", id, delta: scrubber.scrub(rest) });
  };

  const handleEvent = (controller: TransformStreamDefaultController<Uint8Array>, event: string) => {
    const dataLines = event
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""));
    // Text still held back goes out before the turn's closing events.
    const flushAll = () => {
      for (const id of [...pending.keys()]) flushText(controller, id);
    };
    if (!dataLines.length) {
      if (event.trim()) controller.enqueue(encoder.encode(`${event}\n\n`));
      return;
    }
    const payload = dataLines.join("\n");
    let chunk: Chunk;
    try {
      chunk = JSON.parse(payload) as Chunk;
    } catch {
      flushAll();
      controller.enqueue(encoder.encode(`data: ${payload}\n\n`));
      return;
    }
    if (!chunk || typeof chunk !== "object") {
      emit(controller, chunk);
      return;
    }
    if (typeof chunk.toolCallId === "string" && chunk.toolCallId) {
      chunk = { ...chunk, toolCallId: aliasToolCallId(chunk.toolCallId) };
    }
    if (onRawChunk) {
      try {
        onRawChunk(chunk);
      } catch {
        // Memory for the next turn must never break this one.
      }
    }
    if (chunk.type === "text-delta") {
      const id = String(chunk.id ?? "");
      const joined = (pending.get(id) ?? "") + String(chunk.delta ?? "");
      const [ready, rest] = splitAtLastBoundary(joined);
      pending.set(id, rest);
      if (ready) emit(controller, { ...chunk, delta: scrubber.scrub(ready) });
      return;
    }
    if (chunk.type === "text-end") {
      flushText(controller, String(chunk.id ?? ""));
      emit(controller, chunk);
      return;
    }
    if (chunk.type === "finish" || chunk.type === "error" || chunk.type === "abort") flushAll();
    if (chunk.type === "error" && typeof chunk.errorText === "string") {
      emit(controller, { ...chunk, errorText: scrubber.scrub(chunk.errorText) });
      return;
    }
    const next = privatizeChunk(chunk, scrubber);
    if (next) emit(controller, next);
    if (next?.type === "reasoning-start") {
      emit(controller, { type: "reasoning-delta", id: next.id, delta: PRIVATE_REASONING_TEXT });
    }
  };

  return new TransformStream<Uint8Array, Uint8Array>({
    transform(bytes, controller) {
      buffer += decoder.decode(bytes, { stream: true }).replace(/\r\n/g, "\n");
      let at = buffer.indexOf("\n\n");
      while (at !== -1) {
        handleEvent(controller, buffer.slice(0, at));
        buffer = buffer.slice(at + 2);
        at = buffer.indexOf("\n\n");
      }
    },
    flush(controller) {
      buffer += decoder.decode();
      if (buffer.trim()) handleEvent(controller, buffer);
      for (const id of [...pending.keys()]) flushText(controller, id);
    },
  });
}

/** Wrap a streamed chat response for a private session. JSON and empty bodies pass. */
export function privatizeChatResponse(
  res: Response,
  terms: readonly string[] = [],
  onRawChunk?: (chunk: Chunk) => void,
): Response {
  const contentType = res.headers.get("content-type") ?? "";
  if (!res.body || !contentType.includes("text/event-stream")) return res;
  return new Response(res.body.pipeThrough(createPrivateStreamTransform(terms, onRawChunk)), {
    status: res.status,
    statusText: res.statusText,
    headers: res.headers,
  });
}
