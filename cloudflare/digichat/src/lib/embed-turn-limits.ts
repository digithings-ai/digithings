/**
 * Turn-count limits for the embed gate. Kept in a dependency-free, non-"use client"
 * module so both the server route (embed-turn-quota, api/chat) and client components
 * (embed/page) import the SAME numbers — the free/raised caps are a cross-boundary
 * contract (see the trial-gate design spec's Global Constraints).
 */
export const EMBED_FREE_TURN_LIMIT = 3;
export const EMBED_TRIAL_TURN_LIMIT = 100;

/**
 * Usage counter shown under the composer: `used/limit`, counting UP from 0
 * (0/3 → 3/3), matching the pre-2.0 DataTap trial flow. The counter never
 * goes negative and never exceeds the limit; after trial unlock the limit
 * flips to EMBED_TRIAL_TURN_LIMIT and the same usage count continues (e.g.
 * 3/3 → 4/100 once the held fourth question completes).
 */
export function formatEmbedTurnCounter(turns: number, limit: number): string {
  const used = Math.min(Math.max(0, turns), limit);
  return `${used}/${limit}`;
}
