import { describe, expect, it } from 'vitest';
import {
  CASH_ITEM_ID,
  compositionSummary,
  concentration,
  eventMix,
  historicalComposition,
  liveComposition,
  weightGapPp,
} from './book-view';
import { reconcileBook } from './book-reconciliation';
import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from './types';

const pos = (ticker: string, w: number, category: string, thesis_ids: string[] = []): Position => ({
  ticker,
  name: ticker,
  type: 'LONG',
  weight_actual: w,
  current_price: null,
  entry_price: null,
  entry_date: null,
  rationale: '',
  thesis_ids,
  category,
  pm_notes: '',
  stats: {},
});

const theses = [{ id: 'T-1', name: 'Rates fall' } as Thesis];

describe('liveComposition', () => {
  const rec = reconcileBook(
    [pos('AAA', 30, 'equity_broad', ['t-1']), pos('BBB', 20, 'equity_broad'), pos('CCC', 10, 'commodity_gold', ['t-1'])],
    { investedPct: 60 }
  );

  it('groups by ticker and appends cash so the parts sum to 100', () => {
    const items = liveComposition(rec.rows, rec.cashPct, 'ticker', theses);
    expect(items.map((i) => i.id)).toEqual(['AAA', 'BBB', 'CCC', CASH_ITEM_ID]);
    expect(items.reduce((s, i) => s + i.value, 0)).toBeCloseTo(100, 6);
    expect(items[items.length - 1].tone).toBe(0);
  });

  it('aggregates by category with friendly labels', () => {
    const items = liveComposition(rec.rows, rec.cashPct, 'category', theses);
    const broad = items.find((i) => i.id === 'equity_broad');
    expect(broad?.label).toBe('Broad Equity');
    expect(broad?.value).toBeCloseTo(50, 6);
  });

  it('groups by thesis, normalising ids and bucketing the unlinked', () => {
    const items = liveComposition(rec.rows, rec.cashPct, 'thesis', theses);
    const linked = items.find((i) => i.label === 'Rates fall');
    expect(linked?.value).toBeCloseTo(40, 6);
    expect(items.find((i) => i.id === '_unlinked')?.value).toBeCloseTo(20, 6);
  });

  it('splits a multi-thesis holding evenly instead of double counting it', () => {
    const r = reconcileBook([pos('AAA', 40, 'x', ['a', 'b'])], { investedPct: 40 });
    const items = liveComposition(r.rows, r.cashPct, 'thesis', []);
    expect(items.filter((i) => i.id !== CASH_ITEM_ID).map((i) => i.value)).toEqual([20, 20]);
  });

  it('omits cash when the book is fully invested', () => {
    const r = reconcileBook([pos('AAA', 100, 'x')], { investedPct: 100 });
    expect(liveComposition(r.rows, r.cashPct, 'ticker', []).some((i) => i.id === CASH_ITEM_ID)).toBe(false);
  });
});

describe('historicalComposition', () => {
  const h = (date: string, ticker: string, weight_pct: number): PositionHistoryRow => ({
    date,
    ticker,
    weight_pct,
    category: 'equity_broad',
    thesis_id: null,
  });
  const history = [h('2026-09-01', 'AAA', 50), h('2026-09-01', 'BBB', 25), h('2026-09-02', 'AAA', 90)];

  it('uses only the selected date and treats the remainder as cash', () => {
    const items = historicalComposition(history, '2026-09-01', 'ticker', []);
    expect(items.map((i) => [i.id, i.value])).toEqual([
      ['AAA', 50],
      ['BBB', 25],
      [CASH_ITEM_ID, 25],
    ]);
  });

  it('returns nothing for a date with no rows beyond cash', () => {
    const items = historicalComposition(history, '2026-01-01', 'ticker', []);
    expect(items).toEqual([expect.objectContaining({ id: CASH_ITEM_ID, value: 100 })]);
  });
});

describe('concentration', () => {
  it('reports top name, top-5 share and effective number of bets', () => {
    const rec = reconcileBook([pos('A', 50, 'x'), pos('B', 50, 'x')], { investedPct: 100 });
    const c = concentration(rec.rows);
    expect(c.top1?.ticker).toBe('A');
    expect(c.top5Pct).toBeCloseTo(100, 6);
    expect(c.effectiveN).toBeCloseTo(2, 6);
  });
  it('is empty for an empty book', () => {
    expect(concentration([])).toEqual({ top1: null, top5Pct: 0, effectiveN: null });
  });
});

describe('eventMix / weightGapPp / summary', () => {
  it('counts event kinds in stable order and drops zero kinds', () => {
    const ev = (event: DashboardPositionEvent['event']) => ({ event }) as DashboardPositionEvent;
    expect(eventMix([ev('EXIT'), ev('OPEN'), ev('EXIT')]).map((s) => [s.id, s.value])).toEqual([
      ['OPEN', 1],
      ['EXIT', 2],
    ]);
  });
  it('computes the target gap only when a target exists', () => {
    expect(weightGapPp(12, 10)).toBe(2);
    expect(weightGapPp(12, null)).toBeNull();
  });
  it('summarises the largest parts', () => {
    expect(
      compositionSummary([
        { id: 'a', label: 'A', value: 40 },
        { id: 'b', label: 'B', value: 10 },
      ])
    ).toBe('A 40%, B 10%');
    expect(compositionSummary([])).toBe('No allocation to show.');
  });
});
