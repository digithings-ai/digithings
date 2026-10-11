/**
 * Session-scoped artifact links.
 *
 * Decision on DIG-2638: a download link is bound to the chat session that made
 * it. It dies the moment the session is lost, the page reloads, or the session
 * ends. There is deliberately **no fixed time-to-live** - a TTL would keep
 * serving a link after the session that owns it is gone.
 *
 * A session is identified by its conversation id. Two things therefore kill a
 * link, and both are covered by tests in `session-links.test.ts`:
 *
 *   - the session is reloaded or replaced -> the caller re-registers under a
 *     new id, and the old id's links no longer validate;
 *   - the session ends -> `endSession` drops it explicitly.
 *
 * State is in memory only. That is the decision, not a shortcut: a link that
 * survives in a durable store is exactly the "fixed TTL" behaviour that was
 * reversed.
 */
import { randomBytes, timingSafeEqual } from "node:crypto";

interface SessionRecord {
  token: string;
  links: Set<string>;
  /** The client this session belongs to, when one was supplied. */
  clientKey: string | null;
}

const sessions = new Map<string, SessionRecord>();
/** clientKey -> the session id currently live for that client. */
const liveSessionByClient = new Map<string, string>();

const TOKEN_BYTES = 32;

function newToken(): string {
  return randomBytes(TOKEN_BYTES).toString("base64url");
}

/**
 * Register (or re-register) a session and mint its link token.
 *
 * Re-registering the *same* id is idempotent: it returns the same token, so a
 * re-render or a poll does not silently break a link the user is holding.
 *
 * Pass `clientKey` (anything stable for one browser tab or client, e.g. the
 * caller's owner subject) and a *new* session id retires that client's previous
 * session. That is the reload rule from the decision on DIG-2638: the links the
 * pre-reload session minted stop validating at once.
 */
export function registerSession(sessionId: string, clientKey?: string): string {
  const client = clientKey?.trim() || null;
  const existing = sessions.get(sessionId);
  if (existing) {
    // Same session re-registered (a render, a poll): idempotent, and it adopts
    // the client key if this call is the first one to supply it.
    if (client && !existing.clientKey) {
      existing.clientKey = client;
      retireOtherSessionsFor(client, sessionId);
    }
    return existing.token;
  }
  if (client) retireOtherSessionsFor(client, sessionId);
  const token = newToken();
  sessions.set(sessionId, { token, links: new Set(), clientKey: client });
  if (client) liveSessionByClient.set(client, sessionId);
  return token;
}

/**
 * A client can only have one live session. Registering a new one retires the
 * previous: this is what makes a page reload kill the links the pre-reload
 * session minted, instead of leaving them valid until something else ends them.
 */
function retireOtherSessionsFor(client: string, keepSessionId: string): void {
  const previous = liveSessionByClient.get(client);
  if (previous && previous !== keepSessionId) {
    sessions.delete(previous);
  }
  liveSessionByClient.set(client, keepSessionId);
}

/** Session lost / ended. Every link minted under it stops working at once. */
export function endSession(sessionId: string): void {
  const record = sessions.get(sessionId);
  sessions.delete(sessionId);
  if (record?.clientKey && liveSessionByClient.get(record.clientKey) === sessionId) {
    liveSessionByClient.delete(record.clientKey);
  }
}

/** Bind an artifact link to a session. Returns false if the session is unknown. */
export function bindLink(sessionId: string, link: string): boolean {
  const record = sessions.get(sessionId);
  if (!record) return false;
  record.links.add(link);
  return true;
}

/**
 * True only when this exact link was bound to this exact live session. A
 * reload under a new session id, or an ended session, both return false.
 */
export function isLiveSessionLink(sessionId: string, link: string): boolean {
  const record = sessions.get(sessionId);
  if (!record) return false;
  for (const bound of record.links) {
    if (constantTimeEquals(bound, link)) return true;
  }
  return false;
}

export function activeSessionCount(): number {
  return sessions.size;
}

/** Test-only: drop every session so one test cannot see another's state. */
export function resetSessionLinks(): void {
  sessions.clear();
  liveSessionByClient.clear();
}

function constantTimeEquals(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}
