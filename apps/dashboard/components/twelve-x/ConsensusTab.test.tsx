import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import ConsensusTab, { pivotScoreSeries } from './ConsensusTab';
import { TwelveXProvider, type TwelveXContextValue } from './context';

const mockContext: TwelveXContextValue = {
  runDate: '2026-06-22',
  crossLink: () => {},
  openBrief: () => {},
  watchlist: {
    items: [],
    has: () => false,
    toggle: () => {},
    clear: () => {},
    filterOn: false,
    setFilterOn: () => {},
  },
};

/** Minimal snapshot-row factory; only the fields the tab reads are varied. */
function snap(
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
    ...extra,
  };
}

const DATES = [
  '2026-06-17',
  '2026-06-18',
  '2026-06-19',
  '2026-06-20',
  '2026-06-21',
  '2026-06-22',
];

/** A 6-run ascending series for every G10 currency. */
function tenCurrencySeries(): FxConsensusSnapshotRow[] {
  const rows: FxConsensusSnapshotRow[] = [];
  G10_CURRENCIES.forEach((currency, ci) => {
    DATES.forEach((run_date, di) => {
      const score = (ci % 2 === 0 ? 1 : -1) * (0.3 + di * 0.2);
      rows.push(snap(currency, run_date, score));
    });
  });
  return rows;
}

/** The latest snapshot for each currency (last run_date in the fixture). */
function latestFrom(series: FxConsensusSnapshotRow[]): FxConsensusSnapshotRow[] {
  const byCcy = new Map<string, FxConsensusSnapshotRow>();
  for (const r of series) {
    const cur = byCcy.get(r.currency);
    if (!cur || r.run_date > cur.run_date) byCcy.set(r.currency, r);
  }
  return [...byCcy.values()];
}

const EMPTY_DELTAS: ConsensusDeltaSet = {
  runDate: null,
  prevRunDate: null,
  byCurrency: {},
  movers: [],
};

function render(
  props: Partial<Parameters<typeof ConsensusTab>[0]> = {},
): string {
  const series = props.series ?? tenCurrencySeries();
  const latest = props.latest ?? latestFrom(series);
  const tab = createElement(ConsensusTab, {
    series,
    latest,
    latestDate: '2026-06-22',
    deltas: EMPTY_DELTAS,
    intelligenceWhy: { runDate: null, items: [] },
    researchBriefs: [],
    ...props,
  });
  return renderToStaticMarkup(<TwelveXProvider value={mockContext}>{tab}</TwelveXProvider>);
}

/* ----------------------------------------------------------------------- */
/* Pure helper: pivotScoreSeries (Raw vs Average)                          */
/* ----------------------------------------------------------------------- */

describe('pivotScoreSeries', () => {
  const series = tenCurrencySeries();

  it('pivots raw scores to one row per run_date keyed by currency', () => {
    const rows = pivotScoreSeries(series, ['USD', 'EUR']);
    expect(rows).toHaveLength(DATES.length);
    expect(rows.map((r) => r.run_date)).toEqual(DATES);
    expect(rows[0].USD).toBeCloseTo(0.3, 10);
    expect(rows[0].EUR).toBeCloseTo(-0.3, 10);
    expect(rows[rows.length - 1].USD).toBeCloseTo(1.3, 10);
  });

  it('emits null for a run_date a currency has no score on (no fabricated 0)', () => {
    const sparse = [snap('USD', '2026-06-17', 1), snap('EUR', '2026-06-18', -1)];
    const rows = pivotScoreSeries(sparse, ['USD', 'EUR']);
    const usdRow = rows.find((r) => r.run_date === '2026-06-18');
    expect(usdRow?.USD ?? null).toBeNull();
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
 * the table key also holds `timeframe` and `weighted`; the fetch layer pins
 * those two before the tab sees the series, so one row per currency per
 * generation is what reaches `pivotScoreSeries`.
 */
const DUP_DATE = '2026-06-02';
const G1 = '2026-06-17 14:47:45.587511+00';
const G2 = '2026-06-30 23:00:54.339621+00';
const G3 = '2026-07-23 22:43:39.052539+00';

/** Three currencies, so a whole-generation drop would visibly blank a line. */
const PLOT_CURRENCIES = ['USD', 'EUR', 'JPY'];

/** The production three-generation date bracketed by two clean run_dates. */
function threeGenerationSeries(): FxConsensusSnapshotRow[] {
  const rows: FxConsensusSnapshotRow[] = [];
  for (const currency of PLOT_CURRENCIES) {
    rows.push(snap(currency, '2026-06-01', 0.2, { as_of: '2026-06-01T12:00:00Z' }));
    // G1 published all three, G2 only USD/EUR/JPY's predecessors — here the
    // partial middle generation republishes two of the three.
    rows.push(snap(currency, DUP_DATE, 1.9, { as_of: G1 }));
    rows.push(snap(currency, DUP_DATE, -1.9, { as_of: G2 }));
    rows.push(snap(currency, DUP_DATE, 0.31, { as_of: G3 }));
    rows.push(snap(currency, '2026-06-03', 0.6, { as_of: '2026-06-03T12:00:00Z' }));
  }
  return rows;
}

/** Two fixed permutations: no Math.random, so a failure is reproducible. */
function reordered<T>(rows: T[]): T[] {
  const cut = Math.floor(rows.length / 2);
  return [...rows.slice(cut).reverse(), ...rows.slice(0, cut).reverse()];
}

describe('pivotScoreSeries — publish generations', () => {
  it('emits one point per run_date, scored from the newest as_of', () => {
    const rows = pivotScoreSeries(threeGenerationSeries(), PLOT_CURRENCIES);

    expect(rows.map((r) => r.run_date)).toEqual(['2026-06-01', DUP_DATE, '2026-06-03']);
    const dup = rows.find((r) => r.run_date === DUP_DATE)!;
    expect(dup.USD).toBeCloseTo(0.31, 10);
    expect(dup.EUR).toBeCloseTo(0.31, 10);
    expect(dup.JPY).toBeCloseTo(0.31, 10);
  });

  it('does not let a losing generation blank a winning finite score with null', () => {
    const rows = pivotScoreSeries(
      [
        snap('USD', DUP_DATE, 0.31, { as_of: G3 }),
        snap('USD', DUP_DATE, Number.NaN, { as_of: G2 }),
        snap('USD', DUP_DATE, 1.9, { as_of: G1 }),
      ],
      ['USD'],
    );

    expect(rows).toHaveLength(1);
    expect(rows[0].USD).toBeCloseTo(0.31, 10);
  });

  it('still emits null when the winning generation itself has no finite score', () => {
    // The guard resolves the generation, not the score: a genuinely unscored
    // newest generation must read as a gap, not fall back to the stale value.
    const rows = pivotScoreSeries(
      [
        snap('USD', DUP_DATE, 1.9, { as_of: G1 }),
        snap('USD', DUP_DATE, Number.NaN, { as_of: G3 }),
      ],
      ['USD'],
    );

    expect(rows[0].USD).toBeNull();
  });

  it('returns the same rows whatever order the input arrives in', () => {
    const series = threeGenerationSeries();
    const expected = pivotScoreSeries(series, PLOT_CURRENCIES);

    expect(pivotScoreSeries(reordered(series), PLOT_CURRENCIES)).toEqual(expected);
    expect(pivotScoreSeries([...series].reverse(), PLOT_CURRENCIES)).toEqual(expected);
  });
});

/* ----------------------------------------------------------------------- */
/* Sub-nav + view switching                                                */
/* ----------------------------------------------------------------------- */

describe('ConsensusTab sub-nav', () => {
  it('renders a Table | Charts sub-nav', () => {
    const html = render();
    // The view toggle is the canonical shared SegmentedControl (#4306).
    expect(html).toContain('data-slot="segmented"');
    expect(html).toContain('aria-label="Consensus view"');
    expect(html).toContain('>Table</button>');
    expect(html).toContain('>Charts</button>');
  });

  it('defaults to the Table view (Table pressed)', () => {
    const html = render();
    expect(html).toMatch(/aria-pressed="true"[^>]*>Table<\/button>/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>Charts<\/button>/);
  });
});

/* ----------------------------------------------------------------------- */
/* Confluence reads (moved off Today)                                      */
/* ----------------------------------------------------------------------- */

describe('ConsensusTab confluence reads', () => {
  it('renders the confluence reads list when rows are present', () => {
    const html = render({
      confluence: [
        {
          run_date: '2026-06-22',
          rank: 1,
          currency: 'EUR',
          direction: 'bullish',
          score: 0.8,
          components: {},
          as_of: '2026-06-22T12:00:00Z',
        },
        {
          run_date: '2026-06-22',
          rank: 2,
          currency: 'JPY',
          direction: 'bearish',
          score: 0.6,
          components: {},
          as_of: '2026-06-22T12:00:00Z',
        },
      ] as never,
    });
    expect(html).toContain('Confluence reads');
    expect(html).toContain('EUR');
    expect(html).toContain('bullish');
    expect(html).toContain('JPY');
    expect(html).toContain('bearish');
  });

  it('omits the confluence reads section when there are no rows', () => {
    const html = render();
    expect(html).not.toContain('Confluence reads');
  });
});

/* ----------------------------------------------------------------------- */
/* Table view = exactly one ConsensusDataTable                             */
/* ----------------------------------------------------------------------- */

describe('ConsensusTab Table view', () => {
  it('renders the ConsensusDataTable with filter shortcuts', () => {
    const html = render();
    // Filter shortcuts (no variable window controls) — the shared SegmentedControl.
    for (const label of ['All', 'Bullish', 'Bearish', 'Strong']) {
      expect(html).toContain(`>${label}</button>`);
    }
  });

  it('renders exactly ONE <table> (the old standalone latest-table is gone)', () => {
    const html = render();
    const tableCount = (html.match(/<table/g) ?? []).length;
    expect(tableCount).toBe(1);
  });

  it('renders one data row per G10 currency via ConsensusDataTable', () => {
    const html = render();
    const rowCount = (html.match(/data-ccy=/g) ?? []).length;
    expect(rowCount).toBe(G10_CURRENCIES.length);
  });

  it('hides the Charts-view containers when on the Table view', () => {
    const html = render();
    // The line/area chart containers are only mounted in the Charts view.
    expect(html).not.toContain('data-chart="line"');
  });

  it('does NOT render the removed Biggest shift banner', () => {
    const movers: ConsensusDeltaSet['movers'] = [
      { currency: 'USD', scoreNow: 1.3, scoreDelta: 0.4, absDelta: 0.4, direction: 'up' },
    ];
    const html = render({
      deltas: { ...EMPTY_DELTAS, movers },
    });
    expect(html).not.toContain('Biggest shift');
  });
});

/* ----------------------------------------------------------------------- */
/* Charts view (rendered via the initialView prop = controlled state)      */
/* ----------------------------------------------------------------------- */

describe('ConsensusTab Charts view', () => {
  it('shows the single full-width score-over-time chart', () => {
    const html = render({ initialView: 'charts' });
    expect(html).toContain('data-chart="line"');
    expect(html).toContain('Consensus score over time');
  });

  it('does NOT render the removed position-split chart', () => {
    const html = render({ initialView: 'charts' });
    expect(html).not.toContain('data-chart="split"');
    expect(html).not.toContain('Position split over time');
  });

  it('does NOT render the removed day-to-day jump-strip chart', () => {
    const html = render({ initialView: 'charts' });
    expect(html).not.toContain('data-chart="jump-strip"');
    expect(html).not.toContain('Day-to-day |Δscore|');
  });

  it('does NOT render the removed Raw | Average toggle', () => {
    const html = render({ initialView: 'charts' });
    expect(html).not.toContain('data-smooth="raw"');
    expect(html).not.toContain('data-smooth="ma"');
  });

  it('does NOT render currency filter chips', () => {
    const html = render({ initialView: 'charts' });
    // No separate currency selector chips; legend is interactive instead.
    expect(html).not.toContain('data-ccy-chip=');
  });

  it('renders an interactive custom legend with aria-pressed', () => {
    const html = render({ initialView: 'charts' });
    // The legend should have buttons for each currency.
    for (const ccy of G10_CURRENCIES.slice(0, 3)) {
      expect(html).toMatch(new RegExp(`aria-pressed="(true|false)"[^>]*>${ccy}`));
    }
  });

  it('does NOT render the removed Biggest shift card in Charts view', () => {
    const movers: ConsensusDeltaSet['movers'] = [
      { currency: 'JPY', scoreNow: -1.1, scoreDelta: -0.6, absDelta: 0.6, direction: 'down' },
    ];
    const html = render({ initialView: 'charts', deltas: { ...EMPTY_DELTAS, movers } });
    expect(html).not.toContain('Biggest shift');
  });
});
