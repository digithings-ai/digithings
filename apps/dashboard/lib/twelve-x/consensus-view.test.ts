import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from './types';
import type { FxConsensusSnapshotRow } from './types';
import { deriveConsensusRows, orderCurrencies } from './consensus-view';

/** Minimal snapshot-row factory; only the fields the derivation reads matter. */
function snap(
  currency: string,
  run_date: string,
  score: number,
  as_of = `${run_date}T12:00:00Z`,
): FxConsensusSnapshotRow {
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
    as_of,
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
 * The duplicate date below is the ONLY date carrying several generations, and it
 * is not the last one, so a surviving duplicate would both corrupt the
 * trailing-5 window and be picked as `priorActual`.
 */
const DUP_DATE = '2026-06-02';
const G1 = '2026-06-17 14:47:45.587511+00';
const G2 = '2026-06-30 23:00:54.339621+00';
const G3 = '2026-07-23 22:43:39.052539+00';
const MIDDLE_CURRENCIES = ['USD', 'EUR', 'JPY', 'GBP', 'CHF'];

/** The ten currencies the production G1 and G3 generations both published. */
const TEN_CURRENCIES = [...G10_CURRENCIES];

function generation(asOf: string, currencies: readonly string[], scoreBase: number) {
  return currencies.map((currency, i) => snap(currency, DUP_DATE, scoreBase + i / 10, asOf));
}

/**
 * USD over five distinct run_dates. The newest, 2026-06-02, is the
 * three-generation production date; the superseded G1 value is 1.9 and G2 is
 * -1.9, so a surviving duplicate is impossible to miss. It is deliberately the
 * LAST run_date: only then does `priorActual`, which walks back from
 * `points.length - 2`, land on a second generation of the same day.
 *
 *   05-28  0.05        05-31  0.30
 *   05-29  0.10        06-01  0.50
 *   05-30  0.20        06-02  1.9 (G1) / -1.9 (G2) / 0.31 (G3, wins)
 */
function duplicatedSeries(): FxConsensusSnapshotRow[] {
  return [
    snap('USD', '2026-05-28', 0.05),
    snap('USD', '2026-05-29', 0.1),
    snap('USD', '2026-05-30', 0.2),
    snap('USD', '2026-05-31', 0.3),
    snap('USD', '2026-06-01', 0.5),
    snap('USD', DUP_DATE, 1.9, G1),
    snap('USD', DUP_DATE, -1.9, G2),
    snap('USD', DUP_DATE, 0.31, G3),
  ];
}

/**
 * The five distinct dates the trailing-5 window spans: 05-29..06-02, with G3's
 * 0.31 on the newest date. 05-28's 0.05 stays out.
 */
const WINDOW_SCORES = [0.1, 0.2, 0.3, 0.5, 0.31];
const WINDOW_MEAN = WINDOW_SCORES.reduce((a, b) => a + b, 0) / WINDOW_SCORES.length;

/** Two fixed permutations: no Math.random, so a failure is reproducible. */
function reordered<T>(rows: T[]): T[] {
  const cut = Math.floor(rows.length / 2);
  return [...rows.slice(cut).reverse(), ...rows.slice(0, cut).reverse()];
}

describe('deriveConsensusRows — publish generations', () => {
  it('averages one point per run_date, from the newest as_of', () => {
    const usd = deriveConsensusRows(duplicatedSeries())[0]!;

    // Six distinct dates; the trailing-5 window spans the newest five, so
    // 2026-05-28's 0.05 stays out. 2026-06-02 contributes G3's 0.31, not 1.9.
    expect(usd.avgNow).toBeCloseTo(WINDOW_MEAN, 10);
    expect(usd.actualNow).toBeCloseTo(0.31, 10);
  });

  it('spans five distinct run_dates in the trailing-5 window', () => {
    const usd = deriveConsensusRows(duplicatedSeries())[0]!;

    expect(usd.avgNow).toBeCloseTo(WINDOW_MEAN, 10);
    // A surviving duplicate would let 1.9 and -1.9 into the window.
    expect(usd.avgNow).not.toBeCloseTo((0.3 + 0.5 + 1.9 - 1.9 + 0.31) / 5, 10);
    // avgAgo walks 5 runs back, which with one point per date is 2026-05-28.
    expect(usd.avgAgo).toBeCloseTo(0.05, 10);
  });

  it('compares priorChange across distinct run_dates', () => {
    const usd = deriveConsensusRows(duplicatedSeries())[0]!;

    // The prior run of 2026-06-02 is 2026-06-01 (0.5) — not G2's -1.9, which is
    // what an undeduped series produced by walking back from points.length - 2.
    expect(usd.priorActual).toBeCloseTo(0.5, 10);
    expect(usd.priorChange).toBeCloseTo(-0.19, 10); // 0.31 - 0.5
  });

  it('does not mutate the series it was handed', () => {
    const series = duplicatedSeries();
    const before = JSON.stringify(series);
    deriveConsensusRows(series);
    expect(JSON.stringify(series)).toBe(before);
  });

  it('keeps a currency that only an older generation published', () => {
    // G3 dropped CHF; the date is still complete thanks to G2's CHF row, and
    // that row must carry through rather than leaving a hole in the series.
    const series = [
      ...generation(G1, TEN_CURRENCIES, 1),
      ...generation(G2, MIDDLE_CURRENCIES, 2),
      ...generation(G3, TEN_CURRENCIES.filter((c) => c !== 'CHF'), 3),
      snap('USD', '2026-06-03', 0.5),
    ];
    const rows = deriveConsensusRows(series);
    const chf = rows.find((r) => r.currency === 'CHF')!;

    expect(chf).toBeDefined();
    expect(chf.actualNow).toBeCloseTo(2 + MIDDLE_CURRENCIES.indexOf('CHF') / 10, 10);
  });

  it('lets a non-finite losing generation not blank a winning finite score', () => {
    const rows = deriveConsensusRows([
      snap('USD', '2026-06-01', 0.5),
      snap('USD', DUP_DATE, Number.NaN, G2),
      snap('USD', DUP_DATE, 0.31, G3),
    ]);

    expect(rows[0].actualNow).toBeCloseTo(0.31, 10);
    expect(rows[0].avgNow).toBeCloseTo((0.5 + 0.31) / 2, 10);
  });

  it('returns the same rows whatever order the input arrives in', () => {
    const expected = deriveConsensusRows(duplicatedSeries());

    expect(deriveConsensusRows(reordered(duplicatedSeries()))).toEqual(expected);
    expect(deriveConsensusRows([...duplicatedSeries()].reverse())).toEqual(expected);
  });
});
