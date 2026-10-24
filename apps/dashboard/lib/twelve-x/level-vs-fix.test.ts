import { describe, expect, it } from 'vitest';
import {
  buildLevelFixSeries,
  composeFixSeries,
  fixWindowDays,
  normalizeFixPair,
  pairFixSpec,
  type FxFixPoint,
} from './level-vs-fix';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from './types';

describe('normalizeFixPair', () => {
  it('normalizes compact and dashed forms to BASE/QUOTE', () => {
    expect(normalizeFixPair('EURUSD')).toBe('EUR/USD');
    expect(normalizeFixPair('eur-usd')).toBe('EUR/USD');
    expect(normalizeFixPair(' usd/jpy ')).toBe('USD/JPY');
  });
});

describe('pairFixSpec', () => {
  it('covers direct, invert, multiply, and divide pairs', () => {
    expect(pairFixSpec('EUR/USD')).toEqual({ seriesIds: ['FX/EUR'], op: 'direct' });
    expect(pairFixSpec('JPY/USD')).toEqual({ seriesIds: ['FX/JPY'], op: 'invert' });
    expect(pairFixSpec('EUR/JPY')).toEqual({ seriesIds: ['FX/EUR', 'FX/JPY'], op: 'multiply' });
    expect(pairFixSpec('EUR/GBP')).toEqual({ seriesIds: ['FX/EUR', 'FX/GBP'], op: 'divide' });
  });

  it('returns null outside the covered universe', () => {
    expect(pairFixSpec('BTC/USD')).toBeNull();
    expect(pairFixSpec('')).toBeNull();
    expect(pairFixSpec(null)).toBeNull();
  });
});

function pts(dates: string[], fixes: number[]): FxFixPoint[] {
  return dates.map((date, i) => ({ date, fix: fixes[i] }));
}

describe('composeFixSeries', () => {
  it('passes direct legs through in ascending date order', () => {
    const out = composeFixSeries(
      { seriesIds: ['FX/EUR'], op: 'direct' },
      { 'FX/EUR': pts(['2026-06-02', '2026-06-01'], [1.1, 1.0]) },
    );
    expect(out).toEqual([
      { date: '2026-06-01', fix: 1.0 },
      { date: '2026-06-02', fix: 1.1 },
    ]);
  });

  it('inverts, multiplies, and divides leg histories', () => {
    const bySeries = {
      'FX/EUR': pts(['2026-06-01'], [1.2]),
      'FX/GBP': pts(['2026-06-01'], [1.5]),
      'FX/JPY': pts(['2026-06-01'], [150]),
    };
    expect(
      composeFixSeries({ seriesIds: ['FX/EUR'], op: 'invert' }, bySeries),
    ).toEqual([{ date: '2026-06-01', fix: 1 / 1.2 }]);
    expect(
      composeFixSeries({ seriesIds: ['FX/EUR', 'FX/JPY'], op: 'multiply' }, bySeries)[0].fix,
    ).toBeCloseTo(180, 10);
    expect(
      composeFixSeries({ seriesIds: ['FX/EUR', 'FX/GBP'], op: 'divide' }, bySeries)[0].fix,
    ).toBeCloseTo(0.8, 10);
  });

  it('inverts JPY/CAD, JPY/CHF, CHF/CAD at compose time (mirrors twelve-x)', () => {
    const bySeries = {
      'FX/JPY': pts(['2026-06-01'], [150]),
      'FX/CAD': pts(['2026-06-01'], [1.5]),
      'FX/CHF': pts(['2026-06-01'], [0.9]),
    };
    // twelve-x `_compose_history` special-cases these three as
    // `_invert_series(_divide_cross(left, right))` — 1 / (left / right).
    const jpyCad = composeFixSeries(pairFixSpec('JPY/CAD')!, bySeries);
    const jpyChf = composeFixSeries(pairFixSpec('JPY/CHF')!, bySeries);
    const chfCad = composeFixSeries(pairFixSpec('CHF/CAD')!, bySeries);
    expect(jpyCad[0].fix).toBeCloseTo(1 / (150 / 1.5), 12);
    expect(jpyChf[0].fix).toBeCloseTo(1 / (150 / 0.9), 12);
    expect(chfCad[0].fix).toBeCloseTo(1 / (0.9 / 1.5), 12);
    // Guard against the reciprocal bug: the raw divide result must not leak.
    expect(jpyCad[0].fix).not.toBeCloseTo(150 / 1.5, 6);
    expect(jpyChf[0].fix).not.toBeCloseTo(150 / 0.9, 6);
    expect(chfCad[0].fix).not.toBeCloseTo(0.9 / 1.5, 6);
  });

  it('inner-joins on date and drops zero divisors', () => {
    const out = composeFixSeries(
      { seriesIds: ['FX/EUR', 'FX/GBP'], op: 'divide' },
      {
        'FX/EUR': pts(['2026-06-01', '2026-06-02'], [1.2, 1.3]),
        'FX/GBP': pts(['2026-06-01', '2026-06-03'], [0, 1.5]),
      },
    );
    expect(out).toEqual([]);
  });

  it('returns [] when a leg has no history', () => {
    expect(composeFixSeries({ seriesIds: ['FX/EUR'], op: 'direct' }, {})).toEqual([]);
  });
});

function idea(partial: Partial<FxTradeIdeaRow> = {}): FxTradeIdeaRow {
  return {
    run_date: '2026-06-12',
    rank: 1,
    pair: 'EUR/USD',
    direction: 'long',
    title: 'EUR/USD long',
    thesis: '',
    catalyst: '',
    levels: [],
    citations: [],
    as_of: '2026-06-26T00:00:00Z',
    trade_levels: {
      entry_low: { value: '1.0800', provenance: 'broker_quoted', source_ref: 'desk' },
      entry_high: { value: '1.0850', provenance: 'broker_quoted', source_ref: 'desk' },
      stop: { value: '1.0700', provenance: 'broker_quoted', source_ref: 'desk' },
      targets: [{ value: '1.1000', provenance: 'broker_quoted', source_ref: 'desk' }],
      risk_reward: 2,
      status: 'complete',
    },
    ...partial,
  };
}

function evalRow(partial: Partial<FxIdeaEvalRow> = {}): FxIdeaEvalRow {
  return {
    run_date: '2026-06-12',
    rank: 1,
    horizon_days: 0,
    pair: 'EUR/USD',
    direction: 'long',
    status: 'resolved',
    entry_date: '2026-06-13',
    exit_date: '2026-06-18',
    entry_fix: 1.082,
    exit_fix: 1.095,
    ret: null,
    hold_return: 0.012,
    sigma_entry: null,
    hit: true,
    directional_win: true,
    significant_hit: false,
    n_sessions: 4,
    as_of: '2026-06-26T00:00:00Z',
    ...partial,
  };
}

describe('buildLevelFixSeries', () => {
  it('combines flat published levels with the table fix history and anchors', () => {
    const s = buildLevelFixSeries(
      idea(),
      evalRow(),
      pts(['2026-06-13', '2026-06-14'], [1.082, 1.086]),
    );
    expect(s.entryLow).toBeCloseTo(1.08, 10);
    expect(s.entryHigh).toBeCloseTo(1.085, 10);
    expect(s.stop).toBeCloseTo(1.07, 10);
    expect(s.targets).toEqual([1.1]);
    expect(s.points).toHaveLength(2);
    expect(s.anchorsOnly).toBe(false);
    expect(s.entryFix).toBeCloseTo(1.082, 10);
    expect(s.exitFix).toBeCloseTo(1.095, 10);
  });

  it('falls back to anchors-only points when the table has nothing', () => {
    const s = buildLevelFixSeries(idea(), evalRow(), []);
    expect(s.anchorsOnly).toBe(true);
    expect(s.points).toEqual([
      { date: '2026-06-13', fix: 1.082 },
      { date: '2026-06-18', fix: 1.095 },
    ]);
  });

  it('handles missing levels and missing eval gracefully', () => {
    const s = buildLevelFixSeries(idea({ trade_levels: null }), null, []);
    expect(s.entryLow).toBeNull();
    expect(s.targets).toEqual([]);
    expect(s.points).toEqual([]);
    expect(s.anchorsOnly).toBe(false);
  });
});

describe('fixWindowDays', () => {
  it('covers the idea age plus margin for old ideas', () => {
    // 2026-01-01 → 2026-06-12 is 162 days; window must cover it, not stop at 90.
    expect(fixWindowDays('2026-01-01', '2026-06-12')).toBe(162 + 30);
  });

  it('keeps the 90d floor for recent ideas', () => {
    expect(fixWindowDays('2026-06-01', '2026-06-12')).toBe(90);
  });

  it('clamps unparseable run dates to the floor', () => {
    expect(fixWindowDays('not-a-date', '2026-06-12')).toBe(90);
  });
});
