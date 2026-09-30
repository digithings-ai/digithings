import { describe, expect, it } from 'vitest';
import type { TableRow } from './database.types';
import type { ScoredDecisionEpisode } from './decision-scorecard';
import { computeDecisionScorecard } from './decision-scorecard';
import {
  buildDecisionEdgeTrend,
  convictionEdgeBars,
  decisionsForAnalysisPeriod,
  edgeVerdict,
  filterDecisionsByPeriod,
  reviewQueue,
  sampleLabel,
  stanceEdges,
} from './portfolio-decisions-view';

function decision(over: Partial<TableRow<'decision_log'>>): TableRow<'decision_log'> {
  return {
    id: 'd', run_id: 'r', run_date: '2026-07-01', ticker: 'AAA', stance: 'buy', conviction: 3,
    thesis: 't', benchmark: 'SPY', holding_days: 5, status: 'resolved', actual_return: 0.04,
    alpha: 0.02, reflection: 'r', resolved_at: '2026-07-08T16:00:00Z', created_at: '2026-07-01T16:00:00Z',
    ...over,
  };
}

function scored(i: number, alpha = i / 100, stance = 'buy'): ScoredDecisionEpisode {
  return {
    decision: {
      id: `d${i}`, run_date: `2026-07-${String(i).padStart(2, '0')}`, ticker: `T${i}`, stance,
      conviction: 3, holding_days: 5, status: 'resolved', alpha,
    },
    direction: 'bullish',
    directionalAlpha: alpha,
  };
}

describe('periods', () => {
  it('scopes relative to the latest decision date', () => {
    const rows = [
      decision({ id: 'old', run_date: '2025-12-31' }),
      decision({ id: 'ytd', run_date: '2026-01-01' }),
      decision({ id: 'wk', run_date: '2026-07-29' }),
      decision({ id: 'latest', run_date: '2026-08-05' }),
    ];
    expect(filterDecisionsByPeriod(rows, 'ytd').map((r) => r.id)).toEqual(['ytd', 'wk', 'latest']);
    expect(filterDecisionsByPeriod(rows, '1w').map((r) => r.id)).toEqual(['wk', 'latest']);
    expect(filterDecisionsByPeriod(rows, 'all')).toBe(rows);
  });

  it('does not promote an overlapping update into a new decision at a boundary', () => {
    const rows = [
      decision({ id: 'initiating', run_date: '2025-12-31', holding_days: 10 }),
      decision({ id: 'repeat', run_date: '2026-01-02', holding_days: 10 }),
      decision({ id: 'new', ticker: 'BBB', run_date: '2026-02-01' }),
      decision({ id: 'pending', ticker: 'CCC', run_date: '2026-08-05', status: 'pending', alpha: null }),
    ];
    expect(decisionsForAnalysisPeriod(rows, 'ytd').map((r) => r.id)).toEqual(['new', 'pending']);
  });
});

describe('edge derivations', () => {
  it('builds a cumulative mean edge trend in percent, one point per date', () => {
    const trend = buildDecisionEdgeTrend(Array.from({ length: 12 }, (_, i) => scored(i + 1)));
    expect(trend).toHaveLength(12);
    expect(trend[0].value).toBeCloseTo(1, 6);
    expect(trend.at(-1)?.value).toBeCloseTo(6.5, 6);
  });

  it('groups by stance with hit rate, biggest group first', () => {
    const out = stanceEdges([scored(1, 0.02), scored(2, -0.01), scored(3, 0.03, 'sell')]);
    expect(out[0]).toMatchObject({ stance: 'buy', n: 2 });
    expect(out[0].meanAlphaPct).toBeCloseTo(0.5, 6);
    expect(out[0].hitRatePct).toBe(50);
    expect(out[1]).toMatchObject({ stance: 'sell', n: 1, hitRatePct: 100 });
  });

  it('ranks the review queue worst first and caps it', () => {
    const q = reviewQueue(Array.from({ length: 8 }, (_, i) => scored(i + 1, (i - 4) / 100)), 3);
    expect(q.map((e) => e.decision.id)).toEqual(['d1', 'd2', 'd3']);
  });

  it('labels the verdict with accent/warn/mute, never up/down', () => {
    expect(edgeVerdict(1)).toEqual({ label: 'Positive decision edge', tone: 'accent' });
    expect(edgeVerdict(-1)).toEqual({ label: 'Negative decision edge', tone: 'warn' });
    expect(edgeVerdict(0).tone).toBe('mute');
    expect(edgeVerdict(null).label).toBe('Awaiting resolved outcomes');
  });

  it('labels sample size', () => {
    expect([sampleLabel(2), sampleLabel(20), sampleLabel(50)]).toEqual([
      'limited sample', 'moderate sample', 'larger sample',
    ]);
  });

  it('always returns three conviction rows, null for a missing bucket', () => {
    const card = computeDecisionScorecard([
      { id: 'a', conviction: 3, alpha: 0.02, status: 'resolved', stance: 'buy', run_date: '2026-07-01', holding_days: 5 },
    ]);
    expect(card).not.toBeNull();
    const bars = convictionEdgeBars(card!);
    expect(bars.map((b) => b.bucket)).toEqual(['low', 'medium', 'high']);
    expect(bars.filter((b) => b.meanAlphaPct == null).length).toBeGreaterThan(0);
    expect(bars.reduce((s, b) => s + b.n, 0)).toBe(1);
  });
});
