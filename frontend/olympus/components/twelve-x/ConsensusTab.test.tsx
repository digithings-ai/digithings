import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { consensusAverageSeries } from '@/lib/twelve-x/consensus-derive';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import ConsensusTab, { pivotScoreSeries } from './ConsensusTab';

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
  return renderToStaticMarkup(
    createElement(ConsensusTab, {
      series,
      latest,
      latestDate: '2026-06-22',
      deltas: EMPTY_DELTAS,
      ...props,
    }),
  );
}

/* ----------------------------------------------------------------------- */
/* Pure helper: pivotScoreSeries (Raw vs Average)                          */
/* ----------------------------------------------------------------------- */

describe('pivotScoreSeries', () => {
  const series = tenCurrencySeries();

  it('pivots raw scores to one row per run_date keyed by currency', () => {
    const rows = pivotScoreSeries(series, ['USD', 'EUR'], 'raw');
    expect(rows).toHaveLength(DATES.length);
    // Sorted ascending by run_date.
    expect(rows.map((r) => r.run_date)).toEqual(DATES);
    // First run: USD = +0.30, EUR = -0.30 (raw).
    expect(rows[0].USD).toBeCloseTo(0.3, 10);
    expect(rows[0].EUR).toBeCloseTo(-0.3, 10);
    // Last run: USD = +1.30 raw.
    expect(rows[rows.length - 1].USD).toBeCloseTo(1.3, 10);
  });

  it('in average mode plots the trailing consensus-average series, NOT the raw scores', () => {
    const raw = pivotScoreSeries(series, ['USD'], 'raw');
    const avg = pivotScoreSeries(series, ['USD'], 'average');
    expect(avg).toHaveLength(DATES.length);
    // The last run's averaged value must match consensusAverageSeries (window 5).
    const points = series
      .filter((r) => r.currency === 'USD')
      .sort((a, b) => a.run_date.localeCompare(b.run_date))
      .map((r) => ({ score: r.score }));
    const expected = consensusAverageSeries(points, 5);
    const last = avg.length - 1;
    expect(avg[last].USD).toBeCloseTo(expected[last] as number, 10);
    // The averaged last value differs from the raw last value (proving the swap).
    expect(avg[last].USD).not.toBeCloseTo(raw[last].USD as number, 6);
    // USD raw last = 1.30; trailing-5 avg last = 0.90.
    expect(raw[last].USD).toBeCloseTo(1.3, 10);
    expect(avg[last].USD).toBeCloseTo(0.9, 10);
  });

  it('emits null for a run_date a currency has no score on (no fabricated 0)', () => {
    const sparse = [snap('USD', '2026-06-17', 1), snap('EUR', '2026-06-18', -1)];
    const rows = pivotScoreSeries(sparse, ['USD', 'EUR'], 'raw');
    const usdRow = rows.find((r) => r.run_date === '2026-06-18');
    expect(usdRow?.USD ?? null).toBeNull();
  });
});

/* ----------------------------------------------------------------------- */
/* Sub-nav + view switching                                                */
/* ----------------------------------------------------------------------- */

describe('ConsensusTab sub-nav', () => {
  it('renders a Table | Charts sub-nav', () => {
    const html = render();
    expect(html).toContain('data-conview="table"');
    expect(html).toContain('data-conview="charts"');
  });

  it('defaults to the Table view (Table pressed)', () => {
    const html = render();
    expect(html).toMatch(/data-conview="table"[^>]*aria-pressed="true"/);
    expect(html).toMatch(/data-conview="charts"[^>]*aria-pressed="false"/);
  });
});

/* ----------------------------------------------------------------------- */
/* Table view = exactly one ConsensusDataTable                             */
/* ----------------------------------------------------------------------- */

describe('ConsensusTab Table view', () => {
  it('renders the ConsensusDataTable (window control + filter chips)', () => {
    const html = render();
    // Distinctive ConsensusDataTable markers: the avg-window control + chips.
    expect(html.toLowerCase()).toContain('window');
    for (const n of ['3', '5', '10', '20']) {
      expect(html).toContain(`data-n="${n}"`);
    }
    for (const f of ['all', 'bullish', 'bearish', 'strong']) {
      expect(html).toContain(`data-filter="${f}"`);
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
    expect(html).not.toContain('data-chart="split"');
  });

  it('renders the biggest-shift banner when a top mover is present', () => {
    const movers: ConsensusDeltaSet['movers'] = [
      { currency: 'USD', scoreNow: 1.3, scoreDelta: 0.4, absDelta: 0.4, direction: 'up' },
    ];
    const html = render({
      deltas: { ...EMPTY_DELTAS, movers },
    });
    expect(html).toContain('Biggest shift');
    expect(html).toContain('USD');
  });
});

/* ----------------------------------------------------------------------- */
/* Charts view (rendered via the initialView prop = controlled state)      */
/* ----------------------------------------------------------------------- */

describe('ConsensusTab Charts view', () => {
  it('shows the score-over-time line chart container', () => {
    const html = render({ initialView: 'charts' });
    expect(html).toContain('data-chart="line"');
    expect(html).toContain('Consensus score over time');
  });

  it('shows the position-split container side-by-side at lg', () => {
    const html = render({ initialView: 'charts' });
    expect(html).toContain('data-chart="split"');
    expect(html).toContain('Position split over time');
    // The two-up grid uses the lg:grid-cols-2 breakpoint.
    expect(html).toMatch(/lg:grid-cols-2/);
  });

  it('renders the Raw | Average toggle on the line chart (Raw default)', () => {
    const html = render({ initialView: 'charts' });
    expect(html).toContain('data-smooth="raw"');
    expect(html).toContain('data-smooth="ma"');
    expect(html).toMatch(/data-smooth="raw"[^>]*aria-pressed="true"/);
  });

  it('keeps the currency filter chips that drive the line + split', () => {
    const html = render({ initialView: 'charts' });
    // Per-currency chips (All + each G10).
    for (const ccy of G10_CURRENCIES) {
      expect(html).toContain(`>${ccy}<`);
    }
  });

  it('renders the top-mover "Why this weight?" card in the Charts view too', () => {
    const movers: ConsensusDeltaSet['movers'] = [
      { currency: 'JPY', scoreNow: -1.1, scoreDelta: -0.6, absDelta: 0.6, direction: 'down' },
    ];
    const html = render({ initialView: 'charts', deltas: { ...EMPTY_DELTAS, movers } });
    expect(html).toContain('Biggest shift');
  });

  it('plots the averaged series when smoothing = average', () => {
    const html = render({ initialView: 'charts', initialSmooth: 'ma' });
    expect(html).toMatch(/data-smooth="ma"[^>]*aria-pressed="true"/);
    // The smoothing note flips to the trailing-mean copy (never "moving average").
    expect(html.toLowerCase()).toContain('average');
    expect(html.toLowerCase()).not.toContain('moving average');
  });
});
