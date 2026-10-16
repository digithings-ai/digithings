import { describe, expect, it } from 'vitest';
import {
  consensusAverageAt,
  consensusAverageSeries,
  latestConsensusAverages,
  selectLatestCompleteConsensus,
} from './consensus-derive';

const G10 = ['USD', 'EUR', 'JPY', 'GBP', 'CHF', 'CAD', 'AUD', 'NZD', 'SEK', 'NOK'];

describe('selectLatestCompleteConsensus', () => {
  it('skips an incrementally published run in favor of the latest complete G10 run', () => {
    const complete = G10.map((currency) => ({ run_date: '2026-07-15', currency }));
    const partial = [{ run_date: '2026-07-16', currency: 'USD' }];

    const selected = selectLatestCompleteConsensus([...complete, ...partial]);

    expect(selected).toHaveLength(10);
    expect(new Set(selected.map((row) => row.run_date))).toEqual(new Set(['2026-07-15']));
    expect(selected.map((row) => row.currency)).toEqual(G10);
  });

  it('returns the newest partial run when no complete run exists', () => {
    const selected = selectLatestCompleteConsensus([
      { run_date: '2026-07-15', currency: 'EUR' },
      { run_date: '2026-07-16', currency: 'USD' },
    ]);

    expect(selected).toEqual([{ run_date: '2026-07-16', currency: 'USD' }]);
  });
});

/* ----------------------------------------------------------------------- */
/* DIG-319 (DIG-57 leaf 2) — publish generations                            */
/* ----------------------------------------------------------------------- */

/**
 * Fixture provenance: `fx_consensus_snapshot`, `run_date` 2026-06-02, read from
 * production on 2026-10-04. That date holds three generations:
 *   2026-06-17 14:47:45.587511+00  19 rows / 10 currencies
 *   2026-06-30 23:00:54.339621+00   5 rows /  5 currencies  (partial rerun)
 *   2026-07-23 22:43:39.052539+00  23 rows / 10 currencies
 * The stamps keep their 6 fractional-second digits, which is what the database
 * returns. Production holds more than one row per (run_date, currency) because
 * the table key also holds `timeframe` and `weighted`; these callers pin those
 * two first, so one row per currency per generation is what reaches this
 * function. Which five currencies the middle generation republished is a
 * fixture choice.
 *
 * Score is `(generation + 1) / 10 + currencyIndex / 100`, so the winning
 * generation of a currency is readable straight off the value.
 */
const RUN_DATE = '2026-06-02';
const G1 = '2026-06-17 14:47:45.587511+00';
const G2 = '2026-06-30 23:00:54.339621+00';
const G3 = '2026-07-23 22:43:39.052539+00';

const MIDDLE_CURRENCIES = ['USD', 'EUR', 'JPY', 'GBP', 'CHF'];

interface StampedRow {
  run_date: string;
  currency: string;
  as_of: string;
  score: number;
}

function generation(gen: number, asOf: string, currencies: readonly string[]): StampedRow[] {
  return currencies.map((currency) => ({
    run_date: RUN_DATE,
    currency,
    as_of: asOf,
    score: (gen + 1) / 10 + G10.indexOf(currency) / 100,
  }));
}

/** The three-generation production date: 25 rows, oldest generation first. */
const THREE_GENERATIONS: StampedRow[] = [
  ...generation(0, G1, G10),
  ...generation(1, G2, MIDDLE_CURRENCIES),
  ...generation(2, G3, G10),
];

/** Two fixed permutations: no Math.random, so a failure is reproducible. */
function reordered<T>(rows: T[]): T[] {
  const cut = Math.floor(rows.length / 2);
  return [...rows.slice(cut).reverse(), ...rows.slice(0, cut).reverse()];
}

describe('selectLatestCompleteConsensus — publish generations', () => {
  it('returns the newest-as_of row for each of the ten G10 currencies', () => {
    const selected = selectLatestCompleteConsensus(THREE_GENERATIONS);

    expect(selected).toHaveLength(10);
    expect(selected.map((row) => row.currency)).toEqual(G10);
    // Every currency was republished by G3, so G3 wins all ten.
    expect(new Set(selected.map((row) => row.as_of))).toEqual(new Set([G3]));
    // USD: 0.30 from G3, never 0.10 from G1 or 0.20 from G2.
    expect(selected.find((row) => row.currency === 'USD')?.score).toBeCloseTo(0.3, 10);
  });

  it('still returns a currency only an older generation published', () => {
    // Production G3 published all ten. Dropping its CHF row stands in for an
    // incremental newest publish that has not reached CHF yet: CHF must still
    // come back, carrying the newest stamp that did publish it (G2).
    const incremental = THREE_GENERATIONS.filter(
      (row) => !(row.as_of === G3 && row.currency === 'CHF'),
    );

    const selected = selectLatestCompleteConsensus(incremental);

    expect(selected).toHaveLength(10);
    const byCurrency = new Map(selected.map((row) => [row.currency, row]));
    expect(byCurrency.get('CHF')?.as_of).toBe(G2);
    expect(byCurrency.get('CHF')?.score).toBeCloseTo(0.2 + G10.indexOf('CHF') / 100, 10);
    for (const currency of G10.filter((c) => c !== 'CHF')) {
      expect(byCurrency.get(currency)?.as_of).toBe(G3);
    }
  });

  it('never lets an unstamped row hide a stamped one', () => {
    const selected = selectLatestCompleteConsensus([
      ...THREE_GENERATIONS,
      { run_date: RUN_DATE, currency: 'USD', as_of: null, score: 9.9 },
      { run_date: RUN_DATE, currency: 'USD', as_of: 'not-a-date', score: 9.9 },
    ]);

    const usd = selected.find((row) => row.currency === 'USD');
    expect(usd?.as_of).toBe(G3);
    expect(usd?.score).toBeCloseTo(0.3, 10);
  });

  it('keeps the incumbent on an equal as_of tie', () => {
    // Two rows, same (run_date, currency), same stamp: one generation, so the
    // pick only decides which duplicate is seen, never which generation.
    const first: StampedRow = { run_date: RUN_DATE, currency: 'USD', as_of: G3, score: 0.31 };
    const second: StampedRow = { run_date: RUN_DATE, currency: 'USD', as_of: G3, score: 0.32 };
    const selected = selectLatestCompleteConsensus([first, second, ...THREE_GENERATIONS]);

    const usd = selected.find((row) => row.currency === 'USD');
    expect(usd?.score).toBe(0.31);
  });

  it('returns the same rows whatever order the input arrives in', () => {
    const expected = selectLatestCompleteConsensus(THREE_GENERATIONS);

    expect(selectLatestCompleteConsensus(reordered(THREE_GENERATIONS))).toEqual(expected);
    expect(selectLatestCompleteConsensus([...THREE_GENERATIONS].reverse())).toEqual(expected);
  });
});

describe('consensusAverageAt', () => {
  it('returns null for i<0', () => {
    expect(consensusAverageAt([{ score: 1 }], -1)).toBeNull();
  });

  it('returns null for empty series', () => {
    expect(consensusAverageAt([], 0)).toBeNull();
  });

  it('computes a partial mean when fewer than `window` points precede i', () => {
    const series = [{ score: 2 }, { score: 4 }, { score: 6 }];
    // i=2, window 5 → mean of [2,4,6] = 4
    expect(consensusAverageAt(series, 2)).toBe(4);
    // i=0 → just [2]
    expect(consensusAverageAt(series, 0)).toBe(2);
  });

  it('averages exactly `window` points', () => {
    const series = [10, 20, 30, 40, 50].map((score) => ({ score }));
    // i=4, window 5 → mean [10..50] = 30
    expect(consensusAverageAt(series, 4)).toBe(30);
  });

  it('slides the window: only the last `window` points up to i count', () => {
    const series = [0, 0, 0, 0, 0, 100].map((score) => ({ score }));
    // i=5, window 5 → mean of indices 1..5 = [0,0,0,0,100] = 20
    expect(consensusAverageAt(series, 5)).toBe(20);
  });

  it('respects a custom window size', () => {
    const series = [10, 20, 30, 40].map((score) => ({ score }));
    // i=3, window 2 → mean of [30,40] = 35
    expect(consensusAverageAt(series, 3, 2)).toBe(35);
  });

  it('skips non-finite scores and averages only finite points', () => {
    const series = [
      { score: 2 },
      { score: Number.NaN },
      { score: 6 },
      { score: Number.POSITIVE_INFINITY },
    ];
    // i=3, window 5 → finite points [2,6] → mean 4
    expect(consensusAverageAt(series, 3)).toBe(4);
  });

  it('returns null when no finite points are in the window', () => {
    const series = [{ score: Number.NaN }, { score: Number.POSITIVE_INFINITY }];
    expect(consensusAverageAt(series, 1)).toBeNull();
  });
});

describe('consensusAverageSeries', () => {
  it('maps each index to its trailing average', () => {
    const series = [10, 20, 30].map((score) => ({ score }));
    expect(consensusAverageSeries(series)).toEqual([10, 15, 20]);
  });

  it('returns an empty array for an empty series', () => {
    expect(consensusAverageSeries([])).toEqual([]);
  });

  it('respects a custom window', () => {
    const series = [10, 20, 30].map((score) => ({ score }));
    // window 2 → [10, 15, 25]
    expect(consensusAverageSeries(series, 2)).toEqual([10, 15, 25]);
  });
});

describe('latestConsensusAverages', () => {
  it('derives all fields off the last index', () => {
    const series = [10, 20, 30, 40, 50, 60].map((score) => ({ score }));
    const r = latestConsensusAverages(series);
    // last idx 5, window 5 → mean indices 1..5 = [20,30,40,50,60] = 40
    expect(r.avgNow).toBe(40);
    expect(r.actualNow).toBe(60);
    // idx 4, window 5 → mean [10..50] = 30
    expect(r.avgYesterday).toBe(30);
    // idx 0 → [10]
    expect(r.avgAgo).toBe(10);
    // momentum = actualNow - avgNow = 60 - 40 = 20
    expect(r.momentum).toBe(20);
  });

  it('reports positive momentum when actual exceeds the average', () => {
    const series = [0, 0, 0, 0, 100].map((score) => ({ score }));
    const r = latestConsensusAverages(series);
    // avgNow = mean [0,0,0,0,100] = 20, actualNow = 100 → momentum 80 > 0
    expect(r.momentum).toBeGreaterThan(0);
  });

  it('reports negative momentum when actual is below the average', () => {
    const series = [100, 100, 100, 100, 0].map((score) => ({ score }));
    const r = latestConsensusAverages(series);
    // avgNow = 80, actualNow = 0 → momentum -80 < 0
    expect(r.momentum).toBeLessThan(0);
  });

  it('returns all-null for an empty series', () => {
    expect(latestConsensusAverages([])).toEqual({
      avgNow: null,
      actualNow: null,
      avgYesterday: null,
      avgAgo: null,
      momentum: null,
    });
  });

  it('yields null momentum when avgNow is null', () => {
    const series = [{ score: Number.NaN }];
    const r = latestConsensusAverages(series);
    expect(r.avgNow).toBeNull();
    expect(r.momentum).toBeNull();
  });
});
