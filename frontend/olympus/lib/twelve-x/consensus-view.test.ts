import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from './types';
import type { FxConsensusSnapshotRow } from './types';
import { deriveConsensusRows, orderCurrencies } from './consensus-view';

/** Minimal snapshot-row factory; only the fields the derivation reads matter. */
function snap(currency: string, run_date: string, score: number): FxConsensusSnapshotRow {
  return {
    run_date,
    currency,
    timeframe: 'medium',
    horizon_weeks: null,
    weighted: true,
    score,
    confidence: 0.7,
    agreement: 0.6,
    tilt: 0.1,
    n_eff: 5,
    n_brokers: 5,
    n_views: 8,
    bullish_pct: 0.5,
    bearish_pct: 0.3,
    neutral_pct: 0.1,
    watch_pct: 0.1,
    as_of: `${run_date}T12:00:00Z`,
  };
}

describe('orderCurrencies', () => {
  it('orders present G10 currencies in the canonical sequence', () => {
    expect(orderCurrencies(['JPY', 'USD', 'EUR'])).toEqual(['USD', 'EUR', 'JPY']);
  });

  it('appends non-G10 extras alphabetically, after the canonical block', () => {
    expect(orderCurrencies(['XAU', 'EUR', 'USD', 'BTC'])).toEqual(['USD', 'EUR', 'BTC', 'XAU']);
  });

  it('deduplicates repeated inputs', () => {
    expect(orderCurrencies(['USD', 'USD', 'EUR', 'EUR'])).toEqual(['USD', 'EUR']);
  });

  it('is the same order the full G10 fixture yields', () => {
    expect(orderCurrencies([...G10_CURRENCIES].reverse())).toEqual([...G10_CURRENCIES]);
  });
});

describe('deriveConsensusRows', () => {
  const DATES = ['2026-06-17', '2026-06-18', '2026-06-19', '2026-06-20', '2026-06-21', '2026-06-22'];

  /** USD ascends 0.3 → 1.3 over the 6 runs; EUR descends -0.3 → -1.3. */
  function series(): FxConsensusSnapshotRow[] {
    const rows: FxConsensusSnapshotRow[] = [];
    ['USD', 'EUR'].forEach((ccy, ci) => {
      DATES.forEach((d, di) => rows.push(snap(ccy, d, (ci === 0 ? 1 : -1) * (0.3 + di * 0.2))));
    });
    return rows;
  }

  it('emits one row per currency in canonical G10 order', () => {
    const rows = deriveConsensusRows(series());
    expect(rows.map((r) => r.currency)).toEqual(['USD', 'EUR']);
  });

  it('headlines the trailing-5 average and carries the raw latest score', () => {
    const rows = deriveConsensusRows(series());
    const usd = rows.find((r) => r.currency === 'USD')!;
    // Trailing 5 of USD (0.5..1.3): (0.5+0.7+0.9+1.1+1.3)/5 = 0.90; raw latest = 1.30.
    expect(usd.avgNow).toBeCloseTo(0.9, 10);
    expect(usd.actualNow).toBeCloseTo(1.3, 10);
    // Momentum = raw latest − trailing avg.
    expect(usd.momentum).toBeCloseTo(0.4, 10);
  });

  it('labels conviction from the raw latest score via the shared scoreLabel', () => {
    const rows = deriveConsensusRows(series());
    // USD latest +1.30 ≥ strong band → "Strong bull"; EUR latest -1.30 → "Strong bear".
    expect(rows.find((r) => r.currency === 'USD')!.label).toBe('Strong bull');
    expect(rows.find((r) => r.currency === 'EUR')!.label).toBe('Strong bear');
  });

  it('returns an empty array for an empty series', () => {
    expect(deriveConsensusRows([])).toEqual([]);
  });

  it('derives priorActual and priorChange for the trailing-run comparison', () => {
    const rows = deriveConsensusRows(series());
    const usd = rows.find((r) => r.currency === 'USD')!;
    // USD series: 0.3, 0.5, 0.7, 0.9, 1.1, 1.3. Latest is 1.3, prior is 1.1.
    expect(usd.priorActual).toBeCloseTo(1.1, 10);
    expect(usd.priorChange).toBeCloseTo(0.2, 10); // 1.3 - 1.1
  });

  it('sets priorActual and priorChange to null when fewer than 2 points exist', () => {
    const single = [snap('USD', '2026-06-22', 1.0)];
    const rows = deriveConsensusRows(single);
    expect(rows[0].priorActual).toBeNull();
    expect(rows[0].priorChange).toBeNull();
  });
});
