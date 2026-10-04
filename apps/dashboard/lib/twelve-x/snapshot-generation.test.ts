/**
 * DIG-318 (DIG-57 leaf 1) — publish-generation guard for generation-stamped
 * snapshot reads.
 *
 * Fixture provenance: `fx_consensus_snapshot`, `run_date` 2026-06-02, read from
 * production on 2026-10-04. That date holds three generations:
 *   2026-06-17 14:47:45.587511+00  19 rows / 10 currencies
 *   2026-06-30 23:00:54.339621+00   5 rows /  5 currencies  (partial rerun)
 *   2026-07-23 22:43:39.052539+00  23 rows / 10 currencies
 * The stamps keep their 6 fractional-second digits, which is what the database
 * returns. Production holds more than one row per (run_date, currency) because
 * the table key also holds `timeframe` and `weighted`; this fixture holds one
 * row per currency per generation because the callers pin those two first, and
 * the guard under test keys on (run_date, currency) alone. Which five
 * currencies the middle generation republished is a fixture choice.
 */

import { describe, expect, it } from 'vitest';
import {
  asOfMs,
  keepNewestGenerationPerSeriesKey,
  keepNewestPublish,
  newestAsOfMs,
  SNAPSHOT_PUBLISH_WINDOW_MS,
} from './snapshot-generation';

type ConsensusRow = { run_date: string; currency: string; as_of?: string | null; score: number };

const RUN_DATE = '2026-06-02';
const G1 = '2026-06-17 14:47:45.587511+00';
const G2 = '2026-06-30 23:00:54.339621+00';
const G3 = '2026-07-23 22:43:39.052539+00';
const G3_MS = Date.parse('2026-07-23T22:43:39.052Z');

const CURRENCIES = [
  'USD',
  'EUR',
  'JPY',
  'GBP',
  'CHF',
  'CAD',
  'AUD',
  'NZD',
  'SEK',
  'NOK',
] as const;
const MIDDLE_CURRENCIES = ['USD', 'EUR', 'JPY', 'GBP', 'CHF'] as const;

function generation(asOf: string, currencies: readonly string[], scoreBase: number): ConsensusRow[] {
  return currencies.map((currency, i) => ({
    run_date: RUN_DATE,
    currency,
    as_of: asOf,
    score: scoreBase + i / 10,
  }));
}

/** The three-generation production date, 25 rows, newest generation last. */
const THREE_GENERATIONS: ConsensusRow[] = [
  ...generation(G1, CURRENCIES, 1),
  ...generation(G2, MIDDLE_CURRENCIES, 2),
  ...generation(G3, CURRENCIES, 3),
];

const UNUSABLE_STAMPS: Array<{ as_of?: string | null }> = [
  {},
  { as_of: undefined },
  { as_of: null },
  { as_of: '' },
  { as_of: '   ' },
  { as_of: 'not-a-date' },
  { as_of: '2026-13-45 99:99:99+00' },
];

/** Content of a result set, order independent — one line per row. */
function content(rows: Array<{ run_date: string; currency?: string; as_of?: string | null }>): string[] {
  return rows.map((r) => `${r.run_date}|${r.currency ?? '-'}|${r.as_of ?? '-'}`).sort();
}

/** Two fixed permutations: no Math.random, so a failure is reproducible. */
function reordered<T>(rows: T[]): T[] {
  const cut = Math.floor(rows.length / 2);
  return [...rows.slice(cut).reverse(), ...rows.slice(0, cut).reverse()];
}

describe('SNAPSHOT_PUBLISH_WINDOW_MS', () => {
  it('is one publish window of 15 minutes', () => {
    expect(SNAPSHOT_PUBLISH_WINDOW_MS).toBe(900_000);
  });
});

describe('asOfMs', () => {
  it('reads a production timestamptz stamp as epoch ms', () => {
    expect(asOfMs({ as_of: G3 })).toBe(G3_MS);
    expect(asOfMs({ as_of: G1 })).toBe(Date.parse('2026-06-17T14:47:45.587Z'));
  });

  it('returns NaN, never 0 and never a throw, for missing or unusable stamps', () => {
    for (const row of UNUSABLE_STAMPS) {
      const ms = asOfMs(row);
      expect(Number.isNaN(ms)).toBe(true);
      expect(ms).not.toBe(0);
    }
  });

  it('returns NaN for a stamp that is not a string at runtime', () => {
    const odd = { as_of: 1784846619052 } as unknown as { as_of?: string | null };
    expect(Number.isNaN(asOfMs(odd))).toBe(true);
  });

  it('treats one instant written in two offsets as the same stamp', () => {
    // String order would rank the +02 stamp as newer; epoch order must not.
    expect(asOfMs({ as_of: '2026-07-23 22:43:39.052539+02' })).toBe(
      asOfMs({ as_of: '2026-07-23 21:43:39.052539+01' }),
    );
  });
});

describe('newestAsOfMs', () => {
  it('returns null for no rows', () => {
    expect(newestAsOfMs([])).toBeNull();
  });

  it('returns null when no row carries a usable stamp', () => {
    const rows = UNUSABLE_STAMPS.map((r, i) => ({ run_date: RUN_DATE, as_of: r.as_of, i }));
    expect(newestAsOfMs(rows)).toBeNull();
  });

  it('returns the newest stamp over the three generations', () => {
    expect(newestAsOfMs(THREE_GENERATIONS)).toBe(G3_MS);
  });

  it('ignores unusable stamps mixed in with usable ones', () => {
    const rows = [...THREE_GENERATIONS, { run_date: RUN_DATE, as_of: 'not-a-date' }];
    expect(newestAsOfMs(rows)).toBe(G3_MS);
  });
});

describe('keepNewestPublish', () => {
  it('keeps only the newest generation inside the default window', () => {
    const kept = keepNewestPublish(THREE_GENERATIONS);
    expect(kept).toHaveLength(10);
    expect(kept.every((r) => r.as_of === G3)).toBe(true);
  });

  it('respects an explicit windowMs', () => {
    // Exactly the gap between the second and third generation: both kept.
    const twoGenerations = Date.parse('2026-07-23T22:43:39.052Z') - Date.parse('2026-06-30T23:00:54.339Z');
    expect(keepNewestPublish(THREE_GENERATIONS, twoGenerations)).toHaveLength(15);
    // One millisecond short of that gap: the middle generation falls away.
    expect(keepNewestPublish(THREE_GENERATIONS, twoGenerations - 1)).toHaveLength(10);
    // A window wide enough for every generation keeps the whole batch.
    expect(keepNewestPublish(THREE_GENERATIONS, twoGenerations * 10)).toHaveLength(25);
  });

  it('treats the window edge as inside the window', () => {
    const newest = '2026-07-23T22:43:39.052Z';
    const edge = new Date(G3_MS - SNAPSHOT_PUBLISH_WINDOW_MS).toISOString();
    const justOutside = new Date(G3_MS - SNAPSHOT_PUBLISH_WINDOW_MS - 1).toISOString();
    const rows = [
      { run_date: RUN_DATE, as_of: newest },
      { run_date: RUN_DATE, as_of: edge },
      { run_date: RUN_DATE, as_of: justOutside },
    ];
    expect(keepNewestPublish(rows).map((r) => r.as_of)).toEqual([newest, edge]);
  });

  it('drops unstamped rows when at least one usable stamp exists', () => {
    const rows = [
      { run_date: RUN_DATE, as_of: G3 },
      { run_date: RUN_DATE, as_of: null },
      { run_date: RUN_DATE, as_of: 'not-a-date' },
      { run_date: RUN_DATE },
    ];
    expect(keepNewestPublish(rows)).toHaveLength(1);
  });

  it('keeps every row when no stamp is usable at all', () => {
    const rows = UNUSABLE_STAMPS.map((r) => ({ run_date: RUN_DATE, as_of: r.as_of }));
    expect(keepNewestPublish(rows)).toHaveLength(rows.length);
  });

  it('does not mutate the input array', () => {
    const input = [...THREE_GENERATIONS];
    const before = content(input);
    keepNewestPublish(input);
    keepNewestGenerationPerSeriesKey(input);
    expect(input).toHaveLength(THREE_GENERATIONS.length);
    expect(content(input)).toEqual(before);
  });

  it('does not change what it keeps when the input order changes', () => {
    expect(content(keepNewestPublish(reordered(THREE_GENERATIONS)))).toEqual(
      content(keepNewestPublish(THREE_GENERATIONS)),
    );
  });
});

describe('keepNewestGenerationPerSeriesKey', () => {
  it('keeps one row per currency at the newest generation', () => {
    const kept = keepNewestGenerationPerSeriesKey(THREE_GENERATIONS);
    expect(kept).toHaveLength(10);
    expect(kept.map((r) => r.currency).sort()).toEqual([...CURRENCIES].sort());
    expect(kept.every((r) => r.as_of === G3)).toBe(true);
    // The five currencies the middle generation republished are present too.
    for (const currency of MIDDLE_CURRENCIES) {
      expect(kept.some((r) => r.currency === currency && r.as_of === G3)).toBe(true);
    }
  });

  it('keeps the currencies the newest generation never republished', () => {
    // A partial rerun: GBP and NZD missing from the newest generation.
    const partial = THREE_GENERATIONS.filter(
      (r) => r.as_of !== G3 || !['GBP', 'NZD'].includes(r.currency),
    );
    const kept = keepNewestGenerationPerSeriesKey(partial);
    expect(kept).toHaveLength(10);
    const byCurrency = new Map(kept.map((r) => [r.currency, r.as_of]));
    expect(byCurrency.get('USD')).toBe(G3);
    // GBP was last published by the middle generation, NZD only by the first.
    expect(byCurrency.get('GBP')).toBe(G2);
    expect(byCurrency.get('NZD')).toBe(G1);
  });

  it('resolves every run_date on its own', () => {
    const rows = [
      ...THREE_GENERATIONS,
      { run_date: '2026-06-03', currency: 'USD', as_of: G1, score: 9 },
      { run_date: '2026-06-03', currency: 'EUR', as_of: G2, score: 9 },
    ];
    const kept = keepNewestGenerationPerSeriesKey(rows);
    expect(kept).toHaveLength(12);
    const on = (runDate: string, currency: string) =>
      kept.find((r) => r.run_date === runDate && r.currency === currency)?.as_of;
    expect(on(RUN_DATE, 'USD')).toBe(G3);
    expect(on('2026-06-03', 'USD')).toBe(G1);
    expect(on('2026-06-03', 'EUR')).toBe(G2);
  });

  it('keeps the only row of a series key when nothing is stamped', () => {
    const rows = UNUSABLE_STAMPS.map((r, i) => ({ run_date: RUN_DATE, currency: 'USD', as_of: r.as_of, i }));
    expect(keepNewestGenerationPerSeriesKey(rows)).toHaveLength(1);
  });

  it('lets a usable stamp replace an unstamped row of the same series key', () => {
    const stamped = { run_date: RUN_DATE, currency: 'USD', as_of: G2, score: 2 };
    const unstamped = { run_date: RUN_DATE, currency: 'USD', as_of: 'not-a-date', score: 1 };
    expect(keepNewestGenerationPerSeriesKey([unstamped, stamped])).toEqual([stamped]);
    expect(keepNewestGenerationPerSeriesKey([stamped, unstamped])).toEqual([stamped]);
  });

  // Equal stamps are the one case where input order decides, and the rule is the
  // spec's: the incumbent wins. Production stamps every row of a run_date with one
  // as_of, so such rows are duplicates inside a single generation.
  it('keeps the incumbent when two rows of a series key share one stamp', () => {
    const first = { run_date: RUN_DATE, currency: 'USD', as_of: G3, score: 1 };
    const second = { run_date: RUN_DATE, currency: 'USD', as_of: G3, score: 2 };
    expect(keepNewestGenerationPerSeriesKey([first, second])).toEqual([first]);
  });

  it('returns nothing for no rows', () => {
    expect(keepNewestGenerationPerSeriesKey([])).toEqual([]);
  });

  it('does not change what it keeps when the input order changes', () => {
    expect(content(keepNewestGenerationPerSeriesKey(reordered(THREE_GENERATIONS)))).toEqual(
      content(keepNewestGenerationPerSeriesKey(THREE_GENERATIONS)),
    );
  });
});