/**
 * In-memory, per-client-IP free-turn counter for the `trial_form` embed gate.
 *
 * Mirrors the bounded/TTL pattern of bff-rate-limit.ts: bounded key count caps
 * memory; a long TTL (24h) lets the free-3 span a realistic browsing session
 * rather than a rate-limit window. This is deliberately best-effort per the
 * design spec's "in-memory only for now" decision — it resets on deploy/restart
 * and is not shared across replicas. It resists CASUAL circumvention (incognito
 * refresh, cleared localStorage) with zero new infrastructure; it is not an
 * authorization boundary.
 */

import { BoundedTTLMap } from "@/lib/bounded-map";
import {
  EMBED_FREE_TURN_LIMIT,
  EMBED_TRIAL_TURN_LIMIT,
} from "@/lib/embed-turn-limits";

const MAX_QUOTA_KEYS = 10_000;
const QUOTA_TTL_MS = 24 * 60 * 60_000; // 24h

type TurnState = { count: number; limit: number };

const quota = new BoundedTTLMap<string, TurnState>(MAX_QUOTA_KEYS, QUOTA_TTL_MS);

function stateFor(ip: string): TurnState {
  return quota.get(ip) ?? { count: 0, limit: EMBED_FREE_TURN_LIMIT };
}

/** Increment this IP's turn count and return the running total. */
export function recordEmbedTrialTurn(ip: string): { count: number } {
  const s = stateFor(ip);
  const next: TurnState = { count: s.count + 1, limit: s.limit };
  quota.set(ip, next);
  return { count: next.count };
}

/** True once this IP's count has reached its effective cap (free by default). */
export function isOverEmbedTrialLimit(ip: string): boolean {
  const s = stateFor(ip);
  return s.count >= s.limit;
}

/** Raise this IP's cap (client-signaled unlock). Idempotent. */
export function unlockEmbedTrial(
  ip: string,
  raisedLimit: number = EMBED_TRIAL_TURN_LIMIT,
): void {
  const s = stateFor(ip);
  quota.set(ip, { count: s.count, limit: raisedLimit });
}

/** Test hook — clears all quota state. */
export function resetEmbedTrialQuotaForTests(): void {
  quota.clear();
}
