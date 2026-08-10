/** Embed free-tier turn counter (localStorage, per host origin). See `embed/page.tsx` for BYOK unlock. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { logStorageFailure } from "@/lib/storage-debug";
import { EMBED_FREE_TURN_LIMIT, EMBED_TRIAL_TURN_LIMIT } from "@/lib/embed-turn-limits";

export { EMBED_FREE_TURN_LIMIT, EMBED_TRIAL_TURN_LIMIT };
const STORAGE_PREFIX = "digichat_embed_turns:";
const TRIAL_UNLOCK_STORAGE_PREFIX = "digichat_embed_trial_unlocked:";

/**
 * Session-local mirror of the trial-unlock flag. Needed because `useChat`
 * freezes its transport on first render (#1339): `prepareSendMessagesRequest`
 * cannot see a React `trialUnlocked` prop that flips later. Reading this map
 * (and localStorage) at send time is the same pattern as `readEmbedUrlAuth`.
 * Survives private-mode localStorage failures for the current tab only.
 */
const liveTrialUnlocked = new Set<string>();

/**
 * Resolve the host-origin key this embed is running under.
 *
 * @param explicitHost - The embedding page's own origin, passed via the
 * iframe src's `?host=` param (see embed/page.tsx). Always prefer this: the
 * embedding site always knows its own origin reliably, whereas client-side
 * detection below is inherently unreliable for real cross-origin embeds
 * (#1372) — kept only as a fallback for embed snippets that predate the
 * `?host=` param.
 */
export function resolveEmbedHost(explicitHost?: string | null): string {
  if (explicitHost) return explicitHost;
  // In SSR / tests, fall back to a stable default.
  if (typeof window === "undefined") return "unknown";
  try {
    const ref = document.referrer;
    if (ref) return new URL(ref).origin;
  } catch {
    // referrer may be malformed or cross-origin-blocked
  }
  try {
    // Accessing window.parent.location will throw for cross-origin iframes —
    // that's the expected case in production (#1372): a genuine embed is
    // always cross-origin, so this branch is only ever useful for same-origin
    // dev embeds. Never fall back to window.location.origin here — that's
    // this app's OWN origin, never a signal about who is embedding it.
    return window.parent.location.origin;
  } catch {
    return "unknown";
  }
}

function storageKey(host: string): string {
  return `${STORAGE_PREFIX}${host}`;
}

export function readTurns(host: string): number {
  try {
    const raw = localStorage.getItem(storageKey(host));
    if (!raw) return 0;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  } catch (err) {
    logStorageFailure("readTurns", err);
    return 0;
  }
}

export function writeTurns(host: string, value: number): void {
  try {
    localStorage.setItem(storageKey(host), String(Math.max(0, value)));
  } catch (err) {
    logStorageFailure("writeTurns", err);
  }
}

function trialUnlockStorageKey(host: string): string {
  return `${TRIAL_UNLOCK_STORAGE_PREFIX}${host}`;
}

/**
 * Persisted trial-form unlock flag (localStorage, per host origin) — mirrors
 * readTurns/writeTurns above. Without this, `trialUnlocked` would live only
 * in React state while the turn counter it overrides is persisted: after any
 * reload a registered visitor's counter still reads >= limit but the unlock
 * that raised the limit is gone, permanently re-gating them (see page.tsx).
 */
export function readTrialUnlocked(host: string): boolean {
  if (liveTrialUnlocked.has(host)) return true;
  try {
    return localStorage.getItem(trialUnlockStorageKey(host)) === "1";
  } catch (err) {
    logStorageFailure("readTrialUnlocked", err);
    return false;
  }
}

export function writeTrialUnlocked(host: string, value: boolean): void {
  if (value) {
    liveTrialUnlocked.add(host);
  } else {
    liveTrialUnlocked.delete(host);
  }
  try {
    if (value) {
      localStorage.setItem(trialUnlockStorageKey(host), "1");
    } else {
      localStorage.removeItem(trialUnlockStorageKey(host));
    }
  } catch (err) {
    logStorageFailure("writeTrialUnlocked", err);
  }
}

const CHAT_ACCESS_TOKEN_PREFIX = "digichat_embed_chat_token:";

function chatAccessTokenKey(host: string): string {
  return `${CHAT_ACCESS_TOKEN_PREFIX}${host}`;
}

/** Chat-access token for this embed host. Same storage discipline as the unlock flag. */
export function readChatAccessToken(host: string): string | null {
  try {
    return localStorage.getItem(chatAccessTokenKey(host));
  } catch {
    return null;
  }
}

export function writeChatAccessToken(host: string, token: string): void {
  try {
    localStorage.setItem(chatAccessTokenKey(host), token);
  } catch {
    // Blocked storage — the send-time read returns null and the free quota applies.
  }
}

/** Test hook — clears the in-memory unlock mirror (localStorage is per-test). */
export function resetLiveTrialUnlockedForTests(): void {
  liveTrialUnlocked.clear();
}

export type EmbedGate = {
  host: string;
  turns: number;
  limit: number;
  /** True once `turns >= limit` (and BYOK has not unlocked the gate). */
  locked: boolean;
  /** Call after a successful user turn. */
  increment: () => void;
  /** Reset counter for this host (test hook / "start over" affordance). */
  reset: () => void;
};

/**
 * Hook: free-tier gate counter.
 *
 * @param byokUnlocked - when true, `locked` is always false regardless of count.
 * @param explicitHost - see resolveEmbedHost(); the embedding page's own origin.
 * @param limit - override for tests; default EMBED_FREE_TURN_LIMIT.
 */
export function useEmbedGate(
  byokUnlocked: boolean,
  explicitHost?: string | null,
  limit: number = EMBED_FREE_TURN_LIMIT,
): EmbedGate {
  // explicitHost arrives asynchronously (resolved from a searchParams Promise
  // in the caller), so this must react to it changing rather than capture it
  // once at mount — a one-shot useState lazy initializer would freeze on
  // whatever explicitHost was on the very first render (undefined), silently
  // reintroducing #1372 for every message sent afterward.
  const host = useMemo(() => resolveEmbedHost(explicitHost), [explicitHost]);
  // Adjust state during render when `host` changes, rather than in an effect
  // (react-hooks/set-state-in-effect) — this is React's documented pattern
  // for "resetting state when a prop changes" without an extra render pass.
  const [turnsFor, setTurnsFor] = useState<{ host: string; turns: number }>(() => ({
    host,
    turns: readTurns(host),
  }));
  if (turnsFor.host !== host) {
    setTurnsFor({ host, turns: readTurns(host) });
  }
  const turns = turnsFor.turns;
  const setTurns = useCallback(
    (updater: number | ((prev: number) => number)) => {
      setTurnsFor((prev) => ({
        host: prev.host,
        turns: typeof updater === "function" ? updater(prev.turns) : updater,
      }));
    },
    [],
  );

  const increment = useCallback(() => {
    setTurns((prev) => {
      const next = prev + 1;
      writeTurns(host, next);
      return next;
    });
  }, [host, setTurns]);

  const reset = useCallback(() => {
    writeTurns(host, 0);
    setTurns(0);
  }, [host, setTurns]);

  const locked = !byokUnlocked && turns >= limit;

  return useMemo(
    () => ({ host, turns, limit, locked, increment, reset }),
    [host, turns, limit, locked, increment, reset],
  );
}

/** Analytics event surface. No-op today — single call-site for future wiring. */
export type EmbedEvent =
  | "embed_loaded"
  | "embed_turn_submitted"
  | "embed_gate_hit"
  | "embed_byok_saved"
  | "embed_open_full_chat";

export function emit(
  event: EmbedEvent,
  props: Record<string, string | number | boolean> = {},
): void {
  // Intentional no-op. Wire to vendor in a later PR — keep the signature stable.
  // Referencing the args avoids an unused-vars lint while staying side-effect free.
  void event;
  void props;
}
