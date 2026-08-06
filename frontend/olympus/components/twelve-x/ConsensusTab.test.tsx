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
  it('renders the ConsensusDataTable with filter shortcuts', () => {
    const html = render();
    // Filter shortcuts (no variable window controls).
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
