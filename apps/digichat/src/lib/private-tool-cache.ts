/**
 * Private session tool memory, server side.
 *
 * In a private session the browser only ever receives stripped tool steps
 * (`private-stream.ts`): no arguments, no results, a neutral tool name. The
 * client sends its thread back on every turn, so without this the model would
 * see its own earlier tool calls as empty on a follow-up and lose the context
 * a multi-turn conversation needs.
 *
 * While a private turn streams, the full tool call (original name, input,
 * output or error) is kept here, keyed by the chat session and the tool call
 * id. On the next turn of the same session the stripped parts the browser
 * sent back are filled in again before the messages reach the model. The
 * browser never sees the payloads.
 *
 * Storage is process-local with a short TTL, like the chat run lock and the
 * guardrail store: the digichat container holds no KV or Durable Object
 * binding. `installPrivateToolCache` is the seam a host with shared storage
 * would fill. A miss (expired, or another instance) leaves the part as the
 * browser sent it — the stripped step — so it degrades to the old behaviour.
 */

import type { UIMessage } from "ai";
import { BoundedTTLMap } from "@/lib/bounded-map";

/** How long a private turn's tool payloads stay available to the next turn. */
export const PRIVATE_TOOL_TTL_MS = 2 * 60 * 60_000;
const MAX_ENTRIES = 8_192;
/** Larger payloads are not kept (the step stays stripped on follow-up). */
const MAX_ENTRY_CHARS = 256_000;

export type PrivateToolRecord = {
  toolName: string;
  input?: unknown;
  output?: unknown;
  errorText?: string;
  /** True for a `dynamic-tool` part (name in `toolName`, not in the type). */
  dynamic?: boolean;
};

export interface PrivateToolCache {
  get(key: string): PrivateToolRecord | undefined;
  set(key: string, record: PrivateToolRecord): void;
}

class MemoryPrivateToolCache implements PrivateToolCache {
  private readonly map = new BoundedTTLMap<string, PrivateToolRecord>(
    MAX_ENTRIES,
    PRIVATE_TOOL_TTL_MS,
  );
  get(key: string) {
    return this.map.get(key);
  }
  set(key: string, record: PrivateToolRecord) {
    this.map.set(key, record);
  }
  clear() {
    this.map.clear();
  }
}

let store: PrivateToolCache = new MemoryPrivateToolCache();

export function installPrivateToolCache(next: PrivateToolCache): void {
  store = next;
}

/** Test helper — a fresh process-local store. */
export function resetPrivateToolCacheForTests(): void {
  store = new MemoryPrivateToolCache();
}

/**
 * Tool call ids shorter than this are not kept or looked up. The scope can be
 * as wide as a tenant's anonymous visitors (an embed sends no session id), so
 * the id itself has to be unguessable; provider ids (`call_…`, `toolu_…`) are.
 */
const MIN_TOOL_CALL_ID = 8;

/**
 * The scope a private session's tool memory lives under: tenant, owner, and
 * the client's session id when it sends one. Stable across turns of the same
 * chat (unlike the upstream conversation id, which only exists from turn 2).
 */
export function privateToolScope(opts: {
  tenantSlug: string;
  ownerUserSub: string;
  sessionHeader?: string | null;
}): string {
  return `private-tools:${opts.tenantSlug}:${opts.ownerUserSub}:${opts.sessionHeader?.trim() || "-"}`;
}

function entryKey(scope: string, toolCallId: string): string {
  return `${scope}::${toolCallId}`;
}

function fits(record: PrivateToolRecord): boolean {
  try {
    return JSON.stringify(record).length <= MAX_ENTRY_CHARS;
  } catch {
    return false;
  }
}

type RawChunk = Record<string, unknown> & { type?: unknown };

/**
 * A recorder for one private turn. Feed it every raw stream chunk *before*
 * it is stripped; it keeps each tool call's full payload under `scope`.
 */
export function privateToolRecorder(scope: string): (chunk: RawChunk) => void {
  const pending = new Map<string, PrivateToolRecord>();
  const save = (id: string, record: PrivateToolRecord) => {
    pending.set(id, record);
    if (fits(record)) store.set(entryKey(scope, id), record);
  };
  return (chunk) => {
    const id = typeof chunk.toolCallId === "string" ? chunk.toolCallId : "";
    if (id.length < MIN_TOOL_CALL_ID) return;
    const prev = pending.get(id);
    switch (chunk.type) {
      case "tool-input-start":
      case "tool-input-available":
      case "tool-input-error": {
        const record: PrivateToolRecord = {
          ...prev,
          toolName: String(chunk.toolName ?? prev?.toolName ?? ""),
          ...(chunk.dynamic === true ? { dynamic: true } : {}),
        };
        if ("input" in chunk) record.input = chunk.input;
        if (chunk.type === "tool-input-error" && typeof chunk.errorText === "string") {
          record.errorText = chunk.errorText;
        }
        save(id, record);
        return;
      }
      case "tool-output-available":
        if (prev) save(id, { ...prev, output: chunk.output });
        return;
      case "tool-output-error":
        if (prev) save(id, { ...prev, errorText: String(chunk.errorText ?? "") });
        return;
      default:
        return;
    }
  };
}

type ToolPartLike = Record<string, unknown> & {
  type: string;
  toolCallId?: unknown;
};

/**
 * Fill the stripped tool parts the browser sent back with the payloads kept
 * for this session. Parts without a kept record are left as they are.
 */
export function rehydratePrivateToolParts(messages: UIMessage[], scope: string): UIMessage[] {
  let changed = false;
  const next = messages.map((message) => {
    if (message.role !== "assistant" || !Array.isArray(message.parts)) return message;
    let partsChanged = false;
    const parts = message.parts.map((raw) => {
      const part = raw as unknown as ToolPartLike;
      const isTool = part.type === "dynamic-tool" || part.type.startsWith("tool-");
      if (!isTool || typeof part.toolCallId !== "string") return raw;
      if (part.toolCallId.length < MIN_TOOL_CALL_ID) return raw;
      const record = store.get(entryKey(scope, part.toolCallId));
      if (!record) return raw;
      partsChanged = true;
      const out: ToolPartLike = { ...part };
      if (part.type === "dynamic-tool") out.toolName = record.toolName;
      else if (record.toolName) out.type = `tool-${record.toolName}`;
      if ("input" in record) out.input = record.input;
      if (part.state === "output-available" && "output" in record) out.output = record.output;
      if (part.state === "output-error" && record.errorText !== undefined) {
        out.errorText = record.errorText;
      }
      return out as unknown as typeof raw;
    });
    if (!partsChanged) return message;
    changed = true;
    return { ...message, parts };
  });
  return changed ? next : messages;
}
