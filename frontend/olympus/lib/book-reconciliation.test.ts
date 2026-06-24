import { describe, it, expect } from 'vitest';
import { reconcileBook } from './book-reconciliation';
import type { Position } from './types';

const pos = (ticker: string, weight_actual: number): Position => ({
  ticker, name: ticker, type: 'LONG', weight_actual,
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
});
