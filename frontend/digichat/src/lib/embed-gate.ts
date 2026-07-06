/** Embed free-tier turn counter (localStorage, per host origin). See `embed/page.tsx` for BYOK unlock. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { logStorageFailure } from "@/lib/storage-debug";

export const EMBED_FREE_TURN_LIMIT = 3;
const STORAGE_PREFIX = "digichat_embed_turns:";

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
/** Read embed iframe query params from the location search string. */
export function readEmbedParamsFromLocation(search: string): {
  token?: string;
  host?: string;
  accent?: string;
  welcome?: string;
  placeholder?: string;
} {
  const raw = search.startsWith("?") ? search.slice(1) : search;
  const sp = new URLSearchParams(raw);
  const token = sp.get("token")?.trim();
  const host = sp.get("host")?.trim();
  const accent = sp.get("accent")?.trim();
  const welcome = sp.get("welcome")?.trim();
  const placeholder = sp.get("placeholder")?.trim();
  return {
    ...(token ? { token } : {}),
    ...(host ? { host } : {}),
    ...(accent ? { accent } : {}),
    ...(welcome ? { welcome } : {}),
    ...(placeholder ? { placeholder } : {}),
  };
}

/**
 * Resolve the host + token to send on embed POST /api/chat.
 * Always prefers the live iframe URL over React state: useChat keeps the first
 * DefaultChatTransport instance, so closure-captured token/host can be stale
 * when searchParams hydrate after mount.
 */
export function resolveEmbedRequestContext(options: {
  explicitHost?: string | null;
  explicitToken?: string | null;
  locationSearch?: string | null;
}): { host: string; token?: string } {
  const fromUrl = options.locationSearch
    ? readEmbedParamsFromLocation(options.locationSearch)
    : {};
  const host = resolveEmbedHost(fromUrl.host ?? options.explicitHost);
  const token = fromUrl.token ?? (options.explicitToken?.trim() || undefined);
  return { host, token };
}

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
