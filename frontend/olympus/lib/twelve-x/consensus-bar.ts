/**
 * Shared consensus-bar constants and pure helpers for the twelve-x dashboard.
 *
 * Extracted verbatim from the inline definitions in
 * `components/twelve-x/ConsensusTab.tsx` so the divergent-bar math (band
 * thresholds, fill width, tick position, per-currency colors) has a single,
 * testable source of truth. Behavior is identical to the previous inline
 * versions — ConsensusTab can import these unchanged.
 */

import { CURRENCY_COLORS, CURRENCY_FALLBACK } from '../chart-colors';

/** Max absolute consensus score; the bar half-track represents `[0, SCORE_MAX]`. */
export const SCORE_MAX = 2;
/** |score| ≥ STRONG_BAND ⇒ strong conviction. */
export const STRONG_BAND = 1.25;
/** |score| ≥ LEAN_BAND ⇒ directional lean (below ⇒ neutral). */
export const LEAN_BAND = 0.35;

/** Map a currency code to its stable chart color, falling back to slate.
 * Hues live in the sanctioned fixed allowlist (lib/chart-colors.ts, #1402). */
export function currencyColor(ccy: string): string {
  return CURRENCY_COLORS[ccy] ?? CURRENCY_FALLBACK;
}

/** score → P&L text color class (strong/lean bands). */
export function scoreColorClass(score: number): string {
  if (score >= LEAN_BAND) return 'text-up';
  if (score <= -LEAN_BAND) return 'text-down';
  return 'text-ink-soft';
}

/** score → human-readable conviction label. */
export function scoreLabel(score: number): string {
  if (score >= STRONG_BAND) return 'Strong bull';
  if (score >= LEAN_BAND) return 'Bullish lean';
  if (score <= -STRONG_BAND) return 'Strong bear';
  if (score <= -LEAN_BAND) return 'Bearish lean';
  return 'Neutral';
}

/**
 * Bar fill as a percentage of the full track width (each side spans 50%).
 * `min(1, |score| / SCORE_MAX) * 50` ⇒ 0 at a zero score, 50 at ±SCORE_MAX,
 * clamped for magnitudes beyond the max.
 */
export function barFillPct(score: number): number {
  return Math.min(1, Math.abs(score) / SCORE_MAX) * 50;
}

/**
 * Tick (e.g. baseline/marker) position as a percentage from the left edge.
 * `50 + clamp(v, -SCORE_MAX, SCORE_MAX) / SCORE_MAX * 50` ⇒ 50 at 0,
 * 100 at +SCORE_MAX, 0 at -SCORE_MAX, clamped out of range.
 */
export function tickPct(v: number): number {
  const clamped = Math.max(-SCORE_MAX, Math.min(SCORE_MAX, v));
  return 50 + (clamped / SCORE_MAX) * 50;
}
