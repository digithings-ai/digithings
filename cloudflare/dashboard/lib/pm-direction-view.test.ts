import { describe, expect, it } from 'vitest';
import {
  derivePmAction,
  formatPmConfidence,
  parsePmDirectionMemo,
  sortPmRoster,
  type PmDirectionRow,
} from './pm-direction-view';

function row(partial: Partial<PmDirectionRow> & Pick<PmDirectionRow, 'ticker'>): PmDirectionRow {
  return {
    direction: 'long',
    convictionRank: 1,
    narrative: null,
    confidence: null,
    ...partial,
  };
}

describe('parsePmDirectionMemo', () => {
  it('reads date, memo, rank, narrative, and confidence', () => {
    const parsed = parsePmDirectionMemo({
      date: '2026-08-31',
      memo: 'Long gold; fade stretched tech.',
      roster: [
        {
          ticker: 'GLD',
          direction: 'long',
          conviction_rank: 1,
          narrative: 'Ballast while real yields ease.',
          confidence: 0.85,
          forecast_reference: {
            ticker: 'GLD',
            effective_forecast_id: '11111111-1111-1111-1111-111111111111',
            degradation_reason: null,
          },
        },
      ],
    });
    expect(parsed.date).toBe('2026-08-31');
    expect(parsed.memo).toBe('Long gold; fade stretched tech.');
    expect(parsed.roster).toHaveLength(1);
    expect(parsed.roster[0]).toMatchObject({
      ticker: 'GLD',
      direction: 'long',
      convictionRank: 1,
      narrative: 'Ballast while real yields ease.',
      confidence: 0.85,
    });
  });

  it('does not copy forecast_reference or degradation_reason onto parsed rows', () => {
    const parsed = parsePmDirectionMemo({
      roster: [
        {
          ticker: 'SPY',
          direction: 'flat',
          conviction_rank: 2,
          forecast_reference: {
            ticker: 'SPY',
            degradation_reason: 'forecast_unavailable',
          },
        },
      ],
    });
    const keys = Object.keys(parsed.roster[0] ?? {});
    expect(keys).not.toContain('forecast_reference');
    expect(keys).not.toContain('degradation_reason');
    expect(JSON.stringify(parsed.roster)).not.toContain('forecast_unavailable');
  });
});

describe('sortPmRoster', () => {
  it('sorts longs by rank, then flats by rank', () => {
    const sorted = sortPmRoster([
      row({ ticker: 'TLT', direction: 'flat', convictionRank: 2 }),
      row({ ticker: 'QQQ', direction: 'long', convictionRank: 3 }),
      row({ ticker: 'CASH', direction: 'flat', convictionRank: 4 }),
      row({ ticker: 'GLD', direction: 'long', convictionRank: 1 }),
    ]);
    expect(sorted.map((r) => r.ticker)).toEqual(['GLD', 'QQQ', 'TLT', 'CASH']);
  });
});

describe('derivePmAction', () => {
  it('uses prior vs H8 target when rebalance weights are present', () => {
    expect(
      derivePmAction({ direction: 'long', priorWeightPct: 0, targetWeightPct: 8 }),
    ).toBe('buy');
    expect(
      derivePmAction({ direction: 'long', priorWeightPct: 10, targetWeightPct: 10 }),
    ).toBe('hold');
    expect(
      derivePmAction({ direction: 'long', priorWeightPct: 8, targetWeightPct: 0 }),
    ).toBe('sell');
  });

  it('maps rebalance action verbs when present', () => {
    expect(derivePmAction({ direction: 'long', rebalanceAction: 'new' })).toBe('buy');
    expect(derivePmAction({ direction: 'long', rebalanceAction: 'add' })).toBe('buy');
    expect(derivePmAction({ direction: 'long', rebalanceAction: 'hold' })).toBe('hold');
    expect(derivePmAction({ direction: 'long', rebalanceAction: 'trim' })).toBe('hold');
    expect(derivePmAction({ direction: 'flat', rebalanceAction: 'exit' })).toBe('sell');
  });

  it('falls back to prior vs current direction when weights are absent', () => {
    expect(derivePmAction({ direction: 'long', priorDirection: 'flat' })).toBe('buy');
    expect(derivePmAction({ direction: 'long', priorDirection: 'long' })).toBe('hold');
    expect(derivePmAction({ direction: 'flat', priorDirection: 'long' })).toBe('sell');
    expect(derivePmAction({ direction: 'flat', priorDirection: 'flat' })).toBe('hold');
  });

  it('shows long/flat only when there is no prior and no rebalance', () => {
    expect(derivePmAction({ direction: 'long' })).toBe('long');
    expect(derivePmAction({ direction: 'flat' })).toBe('flat');
  });
});

describe('formatPmConfidence', () => {
  it('renders unit-interval confidence as a percent', () => {
    expect(formatPmConfidence(0.85)).toBe('85%');
    expect(formatPmConfidence(0)).toBe('0%');
    expect(formatPmConfidence(1)).toBe('100%');
    expect(formatPmConfidence(null)).toBe('—');
  });
});
