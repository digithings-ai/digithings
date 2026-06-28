"use client";
import type { ChatMessage } from "./useStackChat";

/**
 * Cross-tab handoff for escalating the landing quick-ask into the full DigiChat
 * page. When the inline quick-ask hits a follow-up, it stashes the running
 * transcript plus the new question here and opens `/chat` in a new tab; the page
 * reads-and-clears this on mount and resumes the session.
 *
 * Uses `localStorage`, NOT `sessionStorage`: a `window.open`'d tab gets a fresh
 * session storage, so the handoff would silently vanish. localStorage is shared
 * across tabs of the same origin. We keep nothing in the URL (privacy: user text
 * never lands in a query string or history) and read-and-clear immediately so the
 * payload is one-shot and doesn't leak into a later visit. Stale payloads (a tab
 * never opened) self-expire after a few minutes.
 */
const KEY = "digichat:handoff";
const MAX_AGE_MS = 5 * 60 * 1000;

export interface ChatHandoff {
  messages: ChatMessage[];
  pending: string;
  ts: number;
}

export function writeHandoff(messages: ChatMessage[], pending: string): void {
  try {
    const payload: ChatHandoff = { messages, pending: pending.trim(), ts: Date.now() };
    localStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* storage blocked (private mode / quota) — escalation just opens a fresh chat */
  }
}

/** Read the handoff once and remove it. Returns null if absent, malformed, or stale. */
export function readAndClearHandoff(): ChatHandoff | null {
  try {
    const raw = localStorage.getItem(KEY);
    localStorage.removeItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ChatHandoff;
    if (!parsed || typeof parsed.ts !== "number" || Date.now() - parsed.ts > MAX_AGE_MS) return null;
    if (typeof parsed.pending !== "string" || !Array.isArray(parsed.messages)) return null;
    // Validate per-element shape before this payload is seeded, rendered, and POSTed.
    const wellFormed = parsed.messages.every(
      (m) => m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string",
    );
    if (!wellFormed) return null;
    return parsed;
  } catch {
    return null;
  }
}
