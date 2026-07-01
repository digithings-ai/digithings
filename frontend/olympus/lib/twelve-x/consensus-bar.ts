/**
 * Shared consensus-bar constants and pure helpers for the twelve-x dashboard.
 *
 * Extracted verbatim from the inline definitions in
 * `components/twelve-x/ConsensusTab.tsx` so the divergent-bar math (band
 * thresholds, fill width, tick position, per-currency colors) has a single,
 * testable source of truth. Behavior is identical to the previous inline
 * versions — ConsensusTab can import these unchanged.
 */

/** Max absolute consensus score; the bar half-track represents `[0, SCORE_MAX]`. */
export const SCORE_MAX = 2;
/** |score| ≥ STRONG_BAND ⇒ strong conviction. */
export const STRONG_BAND = 1.25;
/** |score| ≥ LEAN_BAND ⇒ directional lean (below ⇒ neutral). */
export const LEAN_BAND = 0.35;

/** Stable per-currency colors (G10 order). */
const CURRENCY_COLORS: Record<string, string> = {
  USD: '#3B82F6',
  EUR: '#10B981',
  JPY: '#F59E0B',
  GBP: '#EF4444',
  CHF: '#8B5CF6',
  CAD: '#06B6D4',
  AUD: '#F97316',
  NZD: '#EC4899',
  SEK: '#6366F1',
  NOK: '#14B8A6',
};

/** Map a currency code to its stable chart color, falling back to slate. */
export function currencyColor(ccy: string): string {
  return CURRENCY_COLORS[ccy] ?? '#94a3b8';
}

/** score → `.fin-*` text color (strong/lean bands). */
export function scoreColorClass(score: number): string {
  if (score >= LEAN_BAND) return 'text-fin-green';
  if (score <= -LEAN_BAND) return 'text-fin-red';
  return 'text-text-secondary';
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
