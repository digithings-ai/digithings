import { describe, it, expect } from 'vitest';
import { reconcileBook, heldByWeight } from './book-reconciliation';
import type { Position } from './types';

const pos = (ticker: string, weight_actual: number, weight_delta?: number): Position => ({
  ticker, name: ticker, type: 'LONG', weight_actual, weight_delta,
  current_price: null, entry_price: null, entry_date: null,
  rationale: '', thesis_ids: [], category: 'equity', pm_notes: '', stats: {},
});

describe('reconcileBook (F3)', () => {
  it('dedupes a ticker double-counted across buckets (keeps max), normalizes to investedPct', () => {
    // Same EWT counted twice (e.g. "equity" + "international") + IJR → raw sum 150.
    const positions = [pos('EWT', 50), pos('EWT', 50), pos('IJR', 50)];
    const { rows, investedPct, cashPct } = reconcileBook(positions, { investedPct: 75 });
    expect(rows.map((r) => r.ticker)).toEqual(['EWT', 'IJR']);
    // Deduped held = 100 (EWT 50 + IJR 50); normalized to investedPct 75 → 37.5 each.
    expect(rows.find((r) => r.ticker === 'EWT')!.normalizedWeight).toBeCloseTo(37.5, 3);
    expect(investedPct).toBe(75);
    expect(cashPct).toBe(25);
    const sum = rows.reduce((s, r) => s + r.normalizedWeight, 0) + cashPct;
    expect(sum).toBeCloseTo(100, 3);
  });
  it('falls back to the deduped held sum (capped 100) when investedPct is absent', () => {
    const { investedPct, cashPct } = reconcileBook([pos('EWT', 40), pos('IJR', 40)]);
    expect(investedPct).toBe(80);
    expect(cashPct).toBe(20);
  });
  it('never reports a >100% book even on a raw 150% input', () => {
    const { investedPct, cashPct } = reconcileBook([pos('A', 60), pos('B', 60), pos('C', 30)], { investedPct: null });
    expect(investedPct).toBeLessThanOrEqual(100);
    expect(cashPct).toBeGreaterThanOrEqual(0);
    expect(investedPct + cashPct).toBeCloseTo(100, 3);
  });

  it('excludes an explicit CASH row from the held set — no double-discount (#1553)', () => {
    // Live pipeline shape: holdings are already % of NAV (sum 90 = invested_pct)
    // with a CASH row carrying the rest. Folding CASH into heldSum used to shrink
    // every holding by invested/(held+cash) = 0.9 (UUP 40 → 36) and count cash twice.
    const positions = [pos('UUP', 40), pos('TLT', 35), pos('IJR', 15), pos('CASH', 10)];
    const { rows, investedPct, cashPct } = reconcileBook(positions, { investedPct: 90 });
    expect(rows.map((r) => r.ticker)).toEqual(['UUP', 'TLT', 'IJR']); // CASH is not a held row
    expect(rows.find((r) => r.ticker === 'UUP')!.normalizedWeight).toBeCloseTo(40, 3); // true % of NAV, not 36
    expect(investedPct).toBe(90);
    expect(cashPct).toBe(10);
    // The whole book (held + cash) sums to 100 — not 91.
    const book = rows.reduce((s, r) => s + r.normalizedWeight, 0) + cashPct;
    expect(book).toBeCloseTo(100, 3);
  });

  it('carries weight_delta into the normalized basis', () => {
    // held sum 100, investedPct 75 → scale 0.75; a +4pp raw delta scales with it.
    const { rows } = reconcileBook([pos('EWT', 60, 4), pos('IJR', 40)], { investedPct: 75 });
    expect(rows.find((r) => r.ticker === 'EWT')!.normalizedDelta).toBeCloseTo(3, 3);
    expect(rows.find((r) => r.ticker === 'IJR')!.normalizedDelta).toBeNull();
  });

  it('heldByWeight sorts held rows heaviest-first and drops CASH', () => {
    const { rows } = reconcileBook(
      [pos('IJR', 10), pos('UUP', 40), pos('CASH', 10), pos('XLE', 5)],
      { investedPct: 90 }
    );
    expect(heldByWeight(rows).map((r) => r.ticker)).toEqual(['UUP', 'IJR', 'XLE']);
  });
});
