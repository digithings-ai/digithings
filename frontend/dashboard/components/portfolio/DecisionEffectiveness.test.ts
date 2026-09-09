import { describe, expect, it } from 'vitest';
import type { ScoredDecisionEpisode } from '@/lib/decision-scorecard';
import { buildDecisionEdgeTrend } from './DecisionEffectiveness';

function scoredDecision(index: number): ScoredDecisionEpisode {
  return {
    decision: {
      id: `decision-${index}`,
      run_date: `2026-07-${String(index).padStart(2, '0')}`,
      ticker: `T${index}`,
      stance: 'buy',
      conviction: 3,
      holding_days: 5,
      status: 'resolved',
      alpha: index / 100,
    },
    direction: 'bullish',
    directionalAlpha: index / 100,
  };
}

describe('buildDecisionEdgeTrend', () => {
  it('uses every scored decision in the selected period', () => {
    const decisions = Array.from({ length: 12 }, (_, index) => scoredDecision(index + 1));
    const trend = buildDecisionEdgeTrend(decisions);

    expect(trend).toHaveLength(12);
    expect(trend[0]?.value).toBeCloseTo(1, 6);
    expect(trend.at(-1)?.value).toBeCloseTo(6.5, 6);
  });
});