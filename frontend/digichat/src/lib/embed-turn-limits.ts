/**
 * Turn-count limits for the embed gate. Kept in a dependency-free, non-"use client"
 * module so both the server route (embed-turn-quota, api/chat) and client components
 * (embed/page) import the SAME numbers — the free/raised caps are a cross-boundary
 * contract (see the trial-gate design spec's Global Constraints).
 */
export const EMBED_FREE_TURN_LIMIT = 3;
export const EMBED_TRIAL_TURN_LIMIT = 100;

/**
 * Default per-IP seed limit for the SERVER-side quota (embed-turn-quota.ts),
 * deliberately looser than EMBED_FREE_TURN_LIMIT. The client counter is what
 * enforces the advertised "first 3 are free" — it's the source of truth for
 * an honest visitor. The server counter exists only to catch localStorage/
 * incognito bypassers, whose client counter reads 0 turns on every request
 * while an honest NAT/CGNAT neighbour sharing the same egress IP does not. If
 * the server cap matched the client cap of 3, the 4th distinct visitor behind
 * the same shared IP within the 24h TTL would be gated at question 1 — this
 * looser cap still catches a bypasser (whose count climbs indefinitely with
 * no client-side reset) without punishing shared egress.
 */
export const EMBED_TRIAL_SERVER_TURN_LIMIT = 10;
