import { isFirstPartyEmbedHost } from "@/lib/embed-first-party";

export const READY_MESSAGE = { type: "digichat:ready" } as const;
export const SEED_MESSAGE_TYPE = "digichat:seed" as const;
/** Parent shell waits this long for digichat:ready (CF Container cold start). */
export const READY_TIMEOUT_MS = 30_000;
export const MAX_SEED_MESSAGES = 40;
export const MAX_SEED_CONTENT_CHARS = 8000;
export const MAX_SEED_PENDING_CHARS = 4000;
export const MAX_SEED_AGE_MS = 5 * 60 * 1000;

export type SeedChatMessage = { role: "user" | "assistant"; content: string };

export type SeedMessage = {
  type: typeof SEED_MESSAGE_TYPE;
  messages: SeedChatMessage[];
  pending: string;
  ts: number;
};

export function isAllowedSeedParentOrigin(origin: string): boolean {
  return isFirstPartyEmbedHost(origin);
}

function tryParseOrigin(raw: string): string {
  try {
    return new URL(raw).origin;
  } catch {
    return "";
  }
}

/**
 * Target origin for `{ type: "digichat:ready" }` postMessage.
 *
 * Must be the **actual parent page** origin (`ancestorOrigins[0]` / `document.referrer`),
 * not the virtual embed `?host=` tenant key. Virtual hosts such as `occ.digithings.ai`
 * identify the corpus/tenant registry entry but are not browsing contexts — posting
 * ready there is dropped by the browser while digithings.ai never hears the handshake.
 */
export function resolveReadyTargetOrigin(opts: {
  ancestorOrigins?: ArrayLike<string> | null | undefined;
  referrer?: string | null | undefined;
}): string | null {
  const ancestors = opts.ancestorOrigins;
  if (ancestors && ancestors.length > 0) {
    const fromAncestor = tryParseOrigin(String(ancestors[0]));
    if (fromAncestor) return fromAncestor;
  }
  const ref = (opts.referrer ?? "").trim();
  if (ref) {
    const fromReferrer = tryParseOrigin(ref);
    if (fromReferrer) return fromReferrer;
  }
  return null;
}

export function parseSeedMessage(
  event: MessageEvent,
  allowedParentOrigins: ReadonlySet<string>,
): SeedMessage | null {
  if (!allowedParentOrigins.has(event.origin)) return null;
  const data = event.data as Record<string, unknown> | null;
  if (!data || data.type !== SEED_MESSAGE_TYPE) return null;
  if (typeof data.ts !== "number" || Date.now() - data.ts > MAX_SEED_AGE_MS) return null;
  if (typeof data.pending !== "string") return null;
  if (data.pending.length > MAX_SEED_PENDING_CHARS) return null;
  if (!Array.isArray(data.messages) || data.messages.length > MAX_SEED_MESSAGES) return null;
  const messages: SeedChatMessage[] = [];
  for (const raw of data.messages) {
    if (!raw || typeof raw !== "object") return null;
    const m = raw as Record<string, unknown>;
    if (m.role !== "user" && m.role !== "assistant") return null;
    if (typeof m.content !== "string") return null;
    if (m.content.length > MAX_SEED_CONTENT_CHARS) return null;
    messages.push({ role: m.role, content: m.content });
  }
  return {
    type: SEED_MESSAGE_TYPE,
    messages,
    pending: data.pending,
    ts: data.ts,
  };
}
