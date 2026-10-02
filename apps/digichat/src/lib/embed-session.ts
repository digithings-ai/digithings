import type { UIMessage } from "ai";

/**
 * The landing embed and `/chat` are two iframes of the same digichat origin.
 * sessionStorage dies with the iframe, so a fullscreen navigation would open
 * a blank thread. This record lives in localStorage on the digichat origin
 * and is what the next iframe restores.
 */
export const EMBED_SESSION_PREFIX = "digichat_embed_session:";
export const EMBED_SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000;
export const EMBED_SESSION_MAX_MESSAGES = 40;

export type EmbedSessionRecord = {
  v: 1;
  conversationId: string | null;
  messages: UIMessage[];
  ts: number;
};

export function embedSessionKey(host: string): string {
  return `${EMBED_SESSION_PREFIX}${host}`;
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function isMessage(value: unknown): value is UIMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as { role?: unknown; parts?: unknown; id?: unknown };
  return (
    (message.role === "user" || message.role === "assistant" || message.role === "system") &&
    Array.isArray(message.parts)
  );
}

export function readEmbedSession(host: string, now = Date.now()): EmbedSessionRecord | null {
  const store = storage();
  if (!store) return null;
  const key = embedSessionKey(host);
  try {
    const raw = store.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<EmbedSessionRecord>;
    if (parsed.v !== 1 || !Array.isArray(parsed.messages) || typeof parsed.ts !== "number") {
      store.removeItem(key);
      return null;
    }
    if (now - parsed.ts > EMBED_SESSION_MAX_AGE_MS) {
      store.removeItem(key);
      return null;
    }
    if (!parsed.messages.every(isMessage)) {
      store.removeItem(key);
      return null;
    }
    return {
      v: 1,
      conversationId: typeof parsed.conversationId === "string" ? parsed.conversationId : null,
      messages: parsed.messages,
      ts: parsed.ts,
    };
  } catch {
    return null;
  }
}

export function writeEmbedSession(
  host: string,
  conversationId: string | null,
  messages: UIMessage[],
  now = Date.now(),
): void {
  const store = storage();
  if (!store || messages.length === 0) return;
  const record: EmbedSessionRecord = {
    v: 1,
    conversationId,
    messages: messages.slice(-EMBED_SESSION_MAX_MESSAGES),
    ts: now,
  };
  try {
    store.setItem(embedSessionKey(host), JSON.stringify(record));
  } catch {
    /* private mode or quota — the in-memory thread still runs */
  }
}

export function clearEmbedSession(host: string): void {
  const store = storage();
  if (!store) return;
  try {
    store.removeItem(embedSessionKey(host));
  } catch {
    /* ignore */
  }
}
