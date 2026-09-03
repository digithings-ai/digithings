import { describe, expect, it } from 'vitest';
import {
  assembleTradeHistory,
  formatHoldPct,
  type TradeHistoryRow,
} from './trade-history';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from './types';

function idea(partial: Partial<FxTradeIdeaRow> & Pick<FxTradeIdeaRow, 'run_date' | 'rank'>): FxTradeIdeaRow {
  return {
    pair: 'USD/JPY',
    direction: 'long',
    title: 'JPY SHORT — via USD/JPY',
    thesis: 'BoJ on hold while Fed stays hawkish.',
    catalyst: 'FOMC minutes',
    levels: [],
    citations: [],
    trade_levels: {
      entry_low: { value: '148.20', provenance: 'broker_quoted', source_ref: 'desk.md' },
      entry_high: { value: '148.60', provenance: 'broker_quoted', source_ref: 'desk.md' },
      stop: { value: '147.40', provenance: 'broker_quoted', source_ref: 'desk.md' },
      targets: [{ value: '150.50', provenance: 'broker_quoted', source_ref: 'desk.md' }],
    },
    evidence: [],
    as_of: '2026-07-31T00:00:00Z',
    ...partial,
  };
}

function evalRow(
  partial: Partial<FxIdeaEvalRow> & Pick<FxIdeaEvalRow, 'run_date' | 'rank'>,
): FxIdeaEvalRow {
  return {
    horizon_days: 0,
    pair: 'USD/JPY',
    direction: 'long',
    status: 'resolved',
    entry_date: '2026-07-24',
    exit_date: '2026-07-31',
    entry_fix: 147.1,
    exit_fix: 148.9,
    ret: 0.012,
    hold_return: 0.012,
    sigma_entry: 0.005,
    hit: true,
    directional_win: true,
    significant_hit: true,
    n_sessions: 5,
    as_of: '2026-07-31T00:00:00Z',
    ...partial,
  };
}

describe('formatHoldPct', () => {
  it('signs gains, leaves losses to their minus, dashes unknowns', () => {
    expect(formatHoldPct(0.012)).toBe('+1.2%');
    expect(formatHoldPct(-0.003)).toBe('-0.3%');
    expect(formatHoldPct(0)).toBe('0.0%');
    expect(formatHoldPct(null)).toBe('—');
    expect(formatHoldPct(undefined)).toBe('—');
  });
});

describe('assembleTradeHistory', () => {
  it('sorts newest-first and joins eval lifecycle + level bands', () => {
    const rows = assembleTradeHistory(
      [
        idea({ run_date: '2026-07-24', rank: 1 }),
        idea({ run_date: '2026-07-31', rank: 2, pair: 'EUR/GBP', direction: 'short' }),
      ],
      [
        evalRow({ run_date: '2026-07-24', rank: 1 }),
        evalRow({
          run_date: '2026-07-31',
          rank: 2,
          pair: 'EUR/GBP',
          direction: 'short',
          status: 'open',
          exit_date: null,
          exit_fix: null,
          directional_win: null,
          hit: null,
        }),
      ],
    );
    expect(rows).toHaveLength(2);
    expect(rows[0].runDate).toBe('2026-07-31');
    expect(rows[0].lifecycle).toBe('live');
    expect(rows[1].lifecycle).toBe('closed');
    expect(rows[1].directionalWin).toBe(true);
    expect(rows[1].holdReturn).toBeCloseTo(0.012);
    expect(rows[1].entryBand).toBe('148.2–148.6');
    expect(rows[1].stop).toBe('147.4');
    expect(rows[1].target).toBe('150.5');
    expect(rows[1].hasLevels).toBe(true);
  });

  it('marks missing_rates, unscored, and level-less ideas honestly', () => {
    const rows: TradeHistoryRow[] = assembleTradeHistory(
      [
        idea({ run_date: '2026-07-20', rank: 1, trade_levels: {} }),
        idea({ run_date: '2026-07-21', rank: 1, trade_levels: {} }),
      ],
      [evalRow({ run_date: '2026-07-20', rank: 1, status: 'missing_rates', hit: null, directional_win: null })],
    );
    const missing = rows.find((r) => r.runDate === '2026-07-20');
    const unscored = rows.find((r) => r.runDate === '2026-07-21');
    expect(missing?.lifecycle).toBe('no_data');
    expect(missing?.directionalWin).toBeNull();
    expect(unscored?.lifecycle).toBe('unscored');
    expect(unscored?.entryBand).toBeNull();
    expect(unscored?.hasLevels).toBe(false);
  });
});
