/**
 * Shared consensus-bar constants and pure helpers for the twelve-x dashboard.
 *
 * Band thresholds, the score-to-tone mapping and the prop builder for the kit
 * `ScoreBar` (`consensusScoreBarProps`) — one testable source of truth.
 */

/** Max absolute consensus score; the bar half-track represents `[0, SCORE_MAX]`. */
export const SCORE_MAX = 2;
/** |score| ≥ STRONG_BAND ⇒ strong conviction. */
export const STRONG_BAND = 1.25;
/** |score| ≥ LEAN_BAND ⇒ directional lean (below ⇒ neutral). */
export const LEAN_BAND = 0.35;

/**
 * score → sentiment text color class (strong/lean bands). Consensus lean is
 * view sentiment, not P&L — --up/--down stay reserved for signed returns.
 */
export function scoreColorClass(score: number): string {
  if (score >= LEAN_BAND) return 'text-accent';
  if (score <= -LEAN_BAND) return 'text-warn';
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
 * Props for the kit `ScoreBar` on the consensus axis: zero-centred `-SCORE_MAX
 * .. +SCORE_MAX`, accent for a bullish fill and warn for a bearish one (lean is
 * view sentiment, not P&L, so never up/down). Optional `actual` adds one
 * reference tick; a non-finite value draws the empty track.
 */
export function consensusScoreBarProps(
  value: number | null | undefined,
  actual?: { value: number | null | undefined; label: string },
) {
  const v = typeof value === 'number' && Number.isFinite(value) ? value : null;
  return {
    value: v,
    min: -SCORE_MAX,
    max: SCORE_MAX,
    tone: (v !== null && v < 0 ? 'warn' : 'accent') as 'warn' | 'accent',
    ticks: actual ? [{ value: actual.value, label: actual.label, tone: 'ink' as const }] : [],
    format: (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}`,
  };
}
