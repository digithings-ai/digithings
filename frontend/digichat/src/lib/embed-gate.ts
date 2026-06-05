/** Embed free-tier turn counter (localStorage, per host origin). See `embed/page.tsx` for BYOK unlock. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { logStorageFailure } from "@/lib/storage-debug";

export const EMBED_FREE_TURN_LIMIT = 3;
const STORAGE_PREFIX = "digichat_embed_turns:";

/** Resolve the host-origin key this embed is running under. */
export function resolveEmbedHost(): string {
  // In SSR / tests, fall back to a stable default.
  if (typeof window === "undefined") return "unknown";
  try {
    const ref = document.referrer;
    if (ref) return new URL(ref).origin;
  } catch {
    // referrer may be malformed or cross-origin-blocked
  }
  try {
    // Accessing window.parent.location will throw for cross-origin iframes;
    // that's expected in production. The referrer branch above handles that
    // case; this is only useful for same-origin dev embeds.
    return window.parent.location.origin;
  } catch {
    return window.location.origin;
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
 * @param limit - override for tests; default EMBED_FREE_TURN_LIMIT.
 */
export function useEmbedGate(
  byokUnlocked: boolean,
  limit: number = EMBED_FREE_TURN_LIMIT,
): EmbedGate {
  // Lazy initializers run once on mount (client-only in a "use client"
  // component tree). Avoids a setState-in-effect cascade.
  const [host] = useState<string>(() => resolveEmbedHost());
  const [turns, setTurns] = useState<number>(() => readTurns(host));

  const increment = useCallback(() => {
    setTurns((prev) => {
      const next = prev + 1;
      writeTurns(host, next);
      return next;
    });
  }, [host]);

  const reset = useCallback(() => {
    writeTurns(host, 0);
    setTurns(0);
  }, [host]);

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
