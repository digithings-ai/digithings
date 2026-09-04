import { describe, expect, it } from 'vitest';
import {
  assembleTradeHistory,
  biasLabel,
  displayableTradeHistory,
  filterTradeHistory,
  formatHoldPct,
  formatPctRight,
  sortTradeHistory,
  summarizeFilteredTrades,
  tradeResult,
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
    entry_px: 147.1,
    exit_px: 148.9,
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

describe('formatPctRight / biasLabel', () => {
  it('formats percent and bias casing', () => {
    expect(formatPctRight(0.75)).toBe('75%');
    expect(formatPctRight(null)).toBe('—');
    expect(biasLabel('long')).toBe('Long');
    expect(biasLabel('SHORT')).toBe('Short');
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
          exit_px: null,
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

describe('displayableTradeHistory / tradeResult', () => {
  it('keeps right/wrong/live and drops no_data and unscored', () => {
    const rows = assembleTradeHistory(
      [
        idea({ run_date: '2026-07-24', rank: 1 }),
        idea({ run_date: '2026-07-25', rank: 1, pair: 'EUR/USD', direction: 'short' }),
        idea({ run_date: '2026-07-20', rank: 1 }),
        idea({ run_date: '2026-07-21', rank: 1 }),
      ],
      [
        evalRow({ run_date: '2026-07-24', rank: 1 }),
        evalRow({
          run_date: '2026-07-25',
          rank: 1,
          pair: 'EUR/USD',
          direction: 'short',
          status: 'open',
          directional_win: null,
          hit: null,
          hold_return: 0.004,
          n_sessions: 3,
        }),
        evalRow({ run_date: '2026-07-20', rank: 1, status: 'missing_rates', directional_win: null, hit: null }),
      ],
    );
    const shown = displayableTradeHistory(rows);
    expect(shown.map((r) => `${r.runDate}:${tradeResult(r)}`).sort()).toEqual([
      '2026-07-24:right',
      '2026-07-25:live',
    ]);
  });
});

describe('filterTradeHistory + summarizeFilteredTrades', () => {
  const base = displayableTradeHistory(
    assembleTradeHistory(
      [
        idea({ run_date: '2026-07-24', rank: 1 }),
        idea({ run_date: '2026-07-24', rank: 2, pair: 'EUR/USD', direction: 'short' }),
        idea({ run_date: '2026-07-31', rank: 1, pair: 'GBP/USD', direction: 'long' }),
        idea({ run_date: '2026-07-18', rank: 1, pair: 'AUD/USD', direction: 'long' }),
      ],
      [
        evalRow({ run_date: '2026-07-24', rank: 1, hold_return: 0.012, directional_win: true }),
        evalRow({
          run_date: '2026-07-24',
          rank: 2,
          pair: 'EUR/USD',
          direction: 'short',
          hold_return: -0.008,
          directional_win: false,
          hit: false,
        }),
        evalRow({
          run_date: '2026-07-31',
          rank: 1,
          pair: 'GBP/USD',
          status: 'open',
          hold_return: 0.002,
          directional_win: null,
          hit: null,
          n_sessions: 2,
        }),
        evalRow({
          run_date: '2026-07-18',
          rank: 1,
          pair: 'AUD/USD',
          hold_return: 0.0005,
          directional_win: true,
        }),
      ],
    ),
  );

  it('filters wins / pair / board / impact floor and recomputes summary', () => {
    const wins = filterTradeHistory(base, {
      result: 'wins',
      pair: 'all',
      board: 'all',
      minAbsImpact: 0,
    });
    expect(wins).toHaveLength(2);
    expect(wins.every((r) => tradeResult(r) === 'right')).toBe(true);

    const eur = filterTradeHistory(base, {
      result: 'all',
      pair: 'EUR/USD',
      board: 'all',
      minAbsImpact: 0,
    });
    expect(eur).toHaveLength(1);
    expect(eur[0].pair).toBe('EUR/USD');

    const board = filterTradeHistory(base, {
      result: 'all',
      pair: 'all',
      board: '2026-07-24',
      minAbsImpact: 0,
    });
    expect(board).toHaveLength(2);

    const impact = filterTradeHistory(base, {
      result: 'all',
      pair: 'all',
      board: 'all',
      minAbsImpact: 0.001,
    });
    // Drops AUD tiny +0.05% right; keeps live GBP (+0.2%), JPY right, EUR wrong
    expect(impact.map((r) => r.pair).sort()).toEqual(['EUR/USD', 'GBP/USD', 'USD/JPY']);

    const summary = summarizeFilteredTrades(base);
    expect(summary.rightCount).toBe(2);
    expect(summary.wrongCount).toBe(1);
    expect(summary.liveCount).toBe(1);
    expect(summary.pctRight).toBeCloseTo(2 / 3);
    expect(summary.avgReturnRights).toBeCloseTo((0.012 + 0.0005) / 2);
    expect(summary.avgReturnWrongs).toBeCloseTo(-0.008);
  });

  it('sorts by impact descending', () => {
    const sorted = sortTradeHistory(base, 'impact', 'desc');
    const impacts = sorted.map((r) => r.holdReturn);
    expect(impacts[0]).toBeCloseTo(0.012);
    expect(impacts[impacts.length - 1]).toBeCloseTo(-0.008);
  });
});
