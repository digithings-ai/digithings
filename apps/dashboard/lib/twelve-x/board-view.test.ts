import { describe, expect, it } from 'vitest';
import type { FxConsensusSnapshotRow } from './types';
import {
  MIN_TREND_RUNS,
  boardSummary,
  deriveBoardRows,
  stanceFromRow,
  stanceSegments,
} from './board-view';

function row(
  currency: string,
  run_date: string,
  score: number,
  extra: Partial<FxConsensusSnapshotRow> = {},
): FxConsensusSnapshotRow {
  return {
    run_date,
    currency,
    timeframe: 'medium',
    horizon_weeks: null,
    weighted: true,
    score,
    confidence: 0.5,
    agreement: 0.5,
    tilt: 0,
    n_eff: 4,
    n_brokers: 6,
    n_views: 9,
    bullish_pct: 50,
    bearish_pct: 30,
    neutral_pct: 10,
    watch_pct: 10,
    as_of: `${run_date}T00:00:00Z`,
    ...extra,
  };
}

const dates = ['2026-06-17', '2026-06-18', '2026-06-19', '2026-06-20', '2026-06-21', '2026-06-22'];

describe('deriveBoardRows', () => {
  it('orders G10 canonically, sorts history oldest-first and keeps the latest stance', () => {
    const series = [
      ...dates.map((d, i) => row('JPY', d, -0.2 * i)),
      ...dates
        .map((d, i) => row('USD', d, 0.1 * i, i === 5 ? { bullish_pct: 70, bearish_pct: 10 } : {}))
        .reverse(),
    ];
    const rows = deriveBoardRows(series);
    expect(rows.map((r) => r.currency)).toEqual(['USD', 'JPY']);
    const usd = rows[0];
    expect(usd.history).toHaveLength(6);
    expect(usd.history[0]).toBe(0);
    expect(usd.history[5]).toBeCloseTo(0.5);
    expect(usd.stance?.bullish).toBe(70);
    expect(usd.latestRun).toBe('2026-06-22');
    expect(usd.nBrokers).toBe(6);
    expect(usd.hasTrend).toBe(true);
  });

  it('refuses a trend for short series instead of drawing a flat line', () => {
    const rows = deriveBoardRows(dates.slice(0, MIN_TREND_RUNS - 1).map((d) => row('EUR', d, 0.4)));
    expect(rows[0].hasTrend).toBe(false);
    expect(rows[0].history).toHaveLength(MIN_TREND_RUNS - 1);
  });

  it('turns non-finite scores into gaps and dedupes a run_date', () => {
    const series = [
      row('EUR', '2026-06-17', 0.1),
      row('EUR', '2026-06-18', Number.NaN),
      row('EUR', '2026-06-18', Number.NaN),
      row('EUR', '2026-06-19', 0.3),
    ];
    expect(deriveBoardRows(series)[0].history).toEqual([0.1, null, 0.3]);
  });

  it('returns no rows for an empty series', () => {
    expect(deriveBoardRows([])).toEqual([]);
  });
});

describe('stance helpers', () => {
  it('is null when every bucket is empty or missing', () => {
    expect(stanceFromRow(undefined)).toBeNull();
    expect(
      stanceFromRow(row('EUR', dates[0], 0, { bullish_pct: 0, bearish_pct: 0, neutral_pct: 0, watch_pct: 0 })),
    ).toBeNull();
  });

  it('maps stance to accent/warn tones, never up/down', () => {
    const segs = stanceSegments({ bullish: 5, bearish: 3, neutral: 1, watch: 1 });
    expect(segs.map((s) => s.key)).toEqual(['bullish', 'bearish', 'watch', 'neutral']);
    expect(segs.find((s) => s.key === 'bullish')?.tone).toBe('accent');
    expect(segs.find((s) => s.key === 'bearish')?.tone).toBe('warn');
    expect(stanceSegments(null)).toEqual([]);
  });
});

describe('boardSummary', () => {
  it('lists every currency with signed average and label', () => {
    const rows = deriveBoardRows(dates.map((d, i) => row('USD', d, 0.5 + i * 0.2)));
    const text = boardSummary(rows);
    expect(text).toContain('USD +');
    expect(text.toLowerCase()).toContain('bull');
  });
  it('states emptiness', () => {
    expect(boardSummary([])).toContain('no consensus history');
  });
});
