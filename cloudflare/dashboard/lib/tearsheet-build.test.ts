import { describe, expect, it } from 'vitest';
import { buildPerformanceTearsheet } from './observability-queries';
import type { TableRow, ViewRow } from './database.types';

const position = (
  date: string,
  ticker: string,
  weight: number,
  currentPrice: number | null = null,
  entryPrice: number | null = null
): TableRow<'positions'> =>
  ({
    id: `${date}-${ticker}`,
    date,
    ticker,
    name: ticker,
    category: 'equity_broad',
    weight_pct: weight,
    thesis_id: null,
    rationale: null,
    current_price: currentPrice,
    entry_price: entryPrice,
    entry_date: null,
    pm_notes: null,
  });

const attribution = (
  date: string,
  ticker: string,
  contribution: number
): TableRow<'position_attribution'> => ({
  id: `${date}-${ticker}`,
  date,
  ticker,
  sector_bucket: 'Technology',
  weight_pct: 20,
  position_return_pct: contribution / 0.2,
  benchmark_return_pct: 2,
  contribution_pct: contribution,
  selection_effect_pct: contribution - 0.4,
  allocation_effect_pct: 0,
  total_attribution_pct: contribution - 0.4,
  metrics_as_of: date,
  created_at: null,
});

const realized = (
  date: string,
  ticker: string,
  contribution: number
): ViewRow<'public_daily_realized_attribution'> => ({
  date,
  ticker,
  contribution_pct: contribution,
  benchmark_return_pct: 0.2,
  opening_equity: 100,
  closing_equity: 100 + contribution,
  contract: 'daily_realized_attribution',
  period_status: 'final',
});

const metrics: TableRow<'portfolio_metrics'> = {
  id: 'm',
  date: '2026-07-17',
  pnl_pct: 0.5,
  sharpe: 1.2,
  volatility: 10,
  max_drawdown: -3,
  alpha: 4,
  net_return_pct: 12,
  benchmark_return_pct: 8,
  relative_return_pct: 4,
  benchmark_ticker: 'SPY',
  invested_pct: 80,
  generated_at: '2026-07-17T22:00:00Z',
  as_of_date: '2026-07-17',
};

const exitEvent = (date: string, ticker: string, realized: number): TableRow<'position_events'> => ({
  id: `${date}-${ticker}-exit`,
  date,
  ticker,
  event: 'EXIT',
  weight_pct: 0,
  prev_weight_pct: 10,
  cumulative_return_since_event_pct: realized,
  price: 110,
  thesis_id: null,
  reason: null,
  created_at: null,
});

const trimEvent = (
  date: string,
  ticker: string,
  price: number,
  prevWeight: number,
  residualWeight: number
): TableRow<'position_events'> => ({
  id: `${date}-${ticker}-trim`,
  date,
  ticker,
  event: 'TRIM',
  weight_pct: residualWeight,
  prev_weight_pct: prevWeight,
  cumulative_return_since_event_pct: null,
  price,
  thesis_id: null,
  reason: null,
  created_at: null,
});

describe('buildPerformanceTearsheet', () => {
  it('falls back to persisted headline returns when NAV history is too short to derive', () => {
    const result = buildPerformanceTearsheet({
      nav: [{ date: '2026-05-01', nav: 999, cash_pct: 20, invested_pct: 80 }],
      positions: [position('2026-07-17', 'AAA', 20)],
      metrics,
      attribution: [attribution('2026-07-17', 'AAA', 1)],
      events: [],
    });

    expect(result.netReturnPct).toBe(12);
    expect(result.benchmarkReturnPct).toBe(8);
    expect(result.relativeReturnPct).toBe(4);
    expect(result.returnsSource).toBe('persisted');
    expect(result.inceptionDate).toBe('2026-05-01');
    expect(result.currentNav).toBe(999);
  });

  it('builds exact base-zero portfolio return and weighted contribution points', () => {
    const first = { ...position('2026-07-01', 'AAA', 20), current_price: 100 };
    const latest = { ...position('2026-07-17', 'AAA', 20), current_price: 110 };
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-07-01', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-17', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [first, latest],
      metrics,
      attribution: [],
      events: [],
    });

    expect(result.navSeries.map((point) => point.returnPct)).toEqual([0, 6]);
    expect(result.contributionSeries.map((point) => point.returnPct)).toEqual([0, 6]);
    expect(result.contributionSeries.map((point) => point.contributions.AAA)).toEqual([0, 2]);
  });

  it('prefers NAV-derived portfolio return over a conflicting persisted net_return_pct', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-07-01', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-17', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [],
      metrics: {
        ...metrics,
        net_return_pct: 7,
        benchmark_return_pct: null,
        relative_return_pct: null,
      },
      attribution: [],
      benchmarkPrices: [
        { date: '2026-07-02', close: 500 },
        { date: '2026-07-16', close: 510 },
      ],
    });

    expect(result.netReturnPct).toBe(6);
    expect(result.benchmarkReturnPct).toBe(2);
    expect(result.relativeReturnPct).toBe(4);
    expect(result.returnsSource).toBe('mixed');
    expect(result.metricsAsOf).toBe('2026-07-17');
  });

  it('never reports positive since-inception when the base-100 NAV index is under 100', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-06-23', nav: 100, cash_pct: 25, invested_pct: 75 },
        { date: '2026-08-26', nav: 98.5, cash_pct: 25, invested_pct: 75 },
      ],
      positions: [],
      metrics: {
        ...metrics,
        net_return_pct: 1.2, // stale/wrong persisted — must not win
        relative_return_pct: 2,
      },
      attribution: [],
      benchmarkPrices: [
        { ticker: 'SPY', date: '2026-06-23', close: 500 },
        { ticker: 'SPY', date: '2026-08-26', close: 490 },
      ],
    });

    expect(result.currentNav).toBe(98.5);
    expect(result.netReturnPct).toBeLessThan(0);
    expect(result.netReturnPct).toBeCloseTo(-1.5, 6);
  });

  it('derives net return from filtered navSeries even when an early raw row is non-finite', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-07-01', nav: Number.NaN, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-02', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-17', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [],
      metrics: {
        ...metrics,
        net_return_pct: 99,
        benchmark_return_pct: null,
        relative_return_pct: null,
      },
      attribution: [],
    });

    expect(result.netReturnPct).toBe(6);
    expect(result.navSeries.map((p) => p.nav)).toEqual([100, 106]);
  });

  it('builds populated benchmark comparisons aligned to the NAV window', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-07-01', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-02', nav: 103, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-03', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [],
      metrics,
      attribution: [],
      benchmarkPrices: [
        { ticker: 'SPY', date: '2026-07-01', close: 500 },
        { ticker: 'SPY', date: '2026-07-03', close: 510 },
        { ticker: 'QQQ', date: '2026-07-01', close: 400 },
        { ticker: 'QQQ', date: '2026-07-02', close: 412 },
        { ticker: 'EMPTY', date: '2026-07-01', close: 100 },
      ],
    });

    expect(result.benchmarkTicker).toBe('SPY');
    expect(result.netReturnPct).toBe(6);
    expect(result.benchmarkReturnPct).toBe(2);
    expect(result.relativeReturnPct).toBe(4);
    expect(result.benchmarkComparisons).toEqual([
      {
        ticker: 'SPY',
        returnPct: 2,
        series: [
          { date: '2026-07-01', returnPct: 0 },
          { date: '2026-07-02', returnPct: 0 },
          { date: '2026-07-03', returnPct: 2 },
        ],
      },
      {
        ticker: 'QQQ',
        returnPct: 3,
        series: [
          { date: '2026-07-01', returnPct: 0 },
          { date: '2026-07-02', returnPct: 3 },
          { date: '2026-07-03', returnPct: 3 },
        ],
      },
    ]);
  });

  it('uses a clearly labeled live fallback when no persisted metrics row exists', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-07-01', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-17', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [],
      metrics: null,
      attribution: [],
      benchmarkPrices: [
        { date: '2026-07-02', close: 500 },
        { date: '2026-07-16', close: 510 },
      ],
    });

    expect(result.netReturnPct).toBe(6);
    expect(result.benchmarkReturnPct).toBe(2);
    expect(result.relativeReturnPct).toBe(4);
    expect(result.returnsSource).toBe('derived');
    // No portfolio_metrics row — do not stamp metricsAsOf from the NAV tip.
    expect(result.metricsAsOf).toBeNull();
    expect(result.navContract).toBe('legacy_estimate');
  });

  it('partitions full attribution history by the latest current book', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [
        position('2026-06-20', 'OLD', 10, 90, 100),
        position('2026-07-17', 'AAA', 20),
      ],
      metrics,
      attribution: [
        attribution('2026-07-17', 'AAA', 1),
        attribution('2026-07-01', 'AAA', 0.5),
        attribution('2026-06-20', 'OLD', -0.2),
        attribution('2026-06-10', 'OLD', 0.1),
      ],
      events: [exitEvent('2026-06-21', 'OLD', 18.5)],
    });

    expect(result.currentHoldings.map((row) => row.ticker)).toEqual(['AAA']);
    expect(result.currentHoldings[0].attributionDate).toBe('2026-07-17');
    expect(result.historicalHoldings.map((row) => row.ticker)).toEqual(['OLD']);
    expect(result.historicalHoldings[0].attributionDate).toBe('2026-06-21');
    expect(result.historicalHoldings[0].realizedReturnPct).toBe(10);
    expect(result.historicalHoldings[0].disposition).toBe('EXIT');
    expect(result.historicalHoldings[0].weightPct).toBe(10);
  });

  it('includes TRIM fills for still-open names with realized % vs average entry', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [
        position('2026-08-20', 'XLF', 20, 52, 50),
        position('2026-08-27', 'XLF', 15, 55, 50),
      ],
      metrics,
      attribution: [attribution('2026-08-27', 'XLF', 0.4)],
      events: [trimEvent('2026-08-26', 'XLF', 54, 20, 15)],
    });

    expect(result.currentHoldings.map((row) => row.ticker)).toEqual(['XLF']);
    expect(result.historicalHoldings).toHaveLength(1);
    expect(result.historicalHoldings[0]).toMatchObject({
      ticker: 'XLF',
      disposition: 'TRIM',
      weightPct: 5,
      realizedReturnPct: 8,
      attributionDate: '2026-08-26',
    });
  });

  it('fails closed on realized % when average entry is missing', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [position('2026-08-27', 'XLF', 15, 55, null)],
      metrics,
      attribution: [],
      events: [trimEvent('2026-08-26', 'XLF', 54, 20, 15)],
    });

    expect(result.historicalHoldings).toHaveLength(1);
    expect(result.historicalHoldings[0].realizedReturnPct).toBeNull();
    expect(result.historicalHoldings[0].disposition).toBe('TRIM');
  });

  it('lists each EXIT and TRIM event rather than one row per ticker', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [
        position('2026-07-01', 'GLD', 10, 200, 180),
        position('2026-08-01', 'GLD', 6, 210, 180),
        position('2026-08-20', 'GLD', 0, 220, 180),
      ],
      metrics,
      attribution: [],
      events: [
        trimEvent('2026-08-01', 'GLD', 210, 10, 6),
        exitEvent('2026-08-20', 'GLD', 0),
      ],
    });

    expect(result.historicalHoldings.map((row) => row.disposition)).toEqual(['EXIT', 'TRIM']);
    expect(result.historicalHoldings[0].realizedReturnPct).toBeCloseTo((110 / 180 - 1) * 100, 5);
    expect(result.historicalHoldings[1].realizedReturnPct).toBeCloseTo((210 / 180 - 1) * 100, 5);
  });

  it('ignores attribution-only ghosts with no EXIT/TRIM ledger evidence', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [position('2026-07-17', 'AAA', 20)],
      metrics,
      attribution: [
        attribution('2026-07-17', 'AAA', 1),
        attribution('2026-06-20', 'GHOST', -0.2),
      ],
      events: [],
    });

    expect(result.historicalHoldings).toEqual([]);
  });

  it('keeps contribution keys scoped to the latest current book', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-06-20', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-17', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [
        position('2026-06-20', 'OLD', 10, 100),
        position('2026-07-17', 'OLD', 0, 110),
        position('2026-06-20', 'AAA', 20, 100),
        position('2026-07-17', 'AAA', 20, 110),
      ],
      metrics,
      attribution: [],
      events: [],
    });

    expect(Object.keys(result.contributionSeries.at(-1)?.contributions ?? {})).toEqual(['AAA']);
  });

  it('keeps current holdings visible when their attribution row is missing', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [position('2026-07-17', 'AAA', 20)],
      metrics,
      attribution: [],
      events: [],
    });

    expect(result.currentHoldings).toHaveLength(1);
    expect(result.currentHoldings[0]).toMatchObject({
      ticker: 'AAA',
      weightPct: 20,
      unrealizedReturnPct: null,
      realizedReturnPct: null,
      attributionDate: '2026-07-17',
    });
  });

  it('derives open unrealized from entry vs current_price when stored pct is null', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [position('2026-08-27', 'VGK', 20, 92.7, 90.99)],
      metrics,
      attribution: [],
      events: [],
    });

    expect(result.currentHoldings[0]).toMatchObject({
      ticker: 'VGK',
      unrealizedReturnPct: expect.closeTo((92.7 / 90.99 - 1) * 100, 5),
      attributionDate: '2026-08-27',
    });
  });

  it('fills missing marks from holdingMarks (price_history) and stamps AS OF to the close date', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [position('2026-08-27', 'VGK', 20.0551, null, 90.99)],
      metrics,
      attribution: [attribution('2026-08-24', 'VGK', 1)],
      events: [],
      holdingMarks: [{ ticker: 'VGK', date: '2026-08-26', close: 92.7 }],
    });

    expect(result.currentHoldings[0]).toMatchObject({
      ticker: 'VGK',
      weightPct: 20.0551,
      unrealizedReturnPct: expect.closeTo((92.7 / 90.99 - 1) * 100, 5),
      // Mark provenance — not the lagging attribution window.
      attributionDate: '2026-08-26',
    });
    expect(result.holdingsAsOf).toBe('2026-08-27');
  });

  it('fails closed on unrealized when entry exists but no mark is available', () => {
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [position('2026-08-27', 'VGK', 20, null, 90.99)],
      metrics,
      attribution: [attribution('2026-08-24', 'VGK', 1)],
      events: [],
      holdingMarks: [],
    });

    expect(result.currentHoldings[0].unrealizedReturnPct).toBeNull();
    // Still prefer the live book date over attribution for AS OF.
    expect(result.currentHoldings[0].attributionDate).toBe('2026-08-27');
  });

  it('prefers stored unrealized_pnl_pct over recomputing from marks', () => {
    const marked = {
      ...position('2026-08-25', 'VGK', 20, 93.19, 90.99),
      unrealized_pnl_pct: 2.417848,
      metrics_as_of: '2026-08-25',
    };
    const result = buildPerformanceTearsheet({
      nav: [],
      positions: [marked],
      metrics,
      attribution: [],
      events: [],
      holdingMarks: [{ ticker: 'VGK', date: '2026-08-26', close: 99 }],
    });

    expect(result.currentHoldings[0].unrealizedReturnPct).toBeCloseTo(2.417848, 5);
    expect(result.currentHoldings[0].attributionDate).toBe('2026-08-25');
  });

  it('chains legacy and finalized runs without drawing the Sep-8 jump (#3767 / #4014)', () => {
    const nav = [
      { date: '2026-09-06', nav: 100, cash_pct: 20, invested_pct: 80 },
      { date: '2026-09-07', nav: 99.92, cash_pct: 20, invested_pct: 80 },
      { date: '2026-09-08', nav: 110.74928206, cash_pct: 20, invested_pct: 80 },
      { date: '2026-09-09', nav: 111.84928206, cash_pct: 20, invested_pct: 80 },
    ];
    const result = buildPerformanceTearsheet({
      nav,
      positions: [],
      metrics: null,
      attribution: [],
      accountingNav: [
        {
          date: '2026-09-06',
          nav: 100,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: null,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
          series_seam: false,
        },
        {
          date: '2026-09-07',
          nav: 99.92,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: null,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
          series_seam: false,
        },
        {
          date: '2026-09-08',
          nav: 110.74928206,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: null,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: true,
        },
        {
          date: '2026-09-09',
          nav: 111.84928206,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: null,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: false,
        },
      ],
    });

    // Every row plots; the seam row carries flat instead of bridging 99.92 to
    // 110.75, so the legacy history stays visible without the phantom jump.
    expect(result.navSeries.map((point) => point.date)).toEqual([
      '2026-09-06',
      '2026-09-07',
      '2026-09-08',
      '2026-09-09',
    ]);
    expect(result.navSeries[0].returnPct).toBe(0);
    expect(result.navSeries[1].returnPct).toBeCloseTo(-0.08, 5);
    expect(result.navSeries[2].returnPct).toBeCloseTo(-0.08, 5);
    const chained = result.navSeries.at(-1)!.returnPct;
    // ~+0.91% chained from the legacy base — never the +10.8% basis bridge.
    expect(chained).toBeCloseTo(0.9124, 3);
    expect(chained).toBeLessThan(2);
    // The KPI and chart agree across the whole series again (#3935 / #4014).
    expect(result.netReturnPct).toBeCloseTo(chained, 5);
    expect(result.inceptionDate).toBe('2026-09-06');
  });

  it("splices runs with each row's own day return instead of the basis jump (#4014)", () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-07', nav: 99.92, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-08', nav: 110.74928206, cash_pct: 18.16, invested_pct: 81.84 },
        { date: '2026-09-09', nav: 110.27496181, cash_pct: 18.24, invested_pct: 81.76 },
      ],
      positions: [],
      metrics: null,
      attribution: [],
      events: [],
      accountingNav: [
        {
          date: '2026-09-07',
          nav: 99.92,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: 0,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
          series_seam: false,
        },
        {
          date: '2026-09-08',
          nav: 110.74928206,
          cash_pct: 18.16,
          invested_pct: 81.84,
          day_return_pct: -1.102422,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: true,
        },
        {
          date: '2026-09-09',
          nav: 110.27496181,
          cash_pct: 18.24,
          invested_pct: 81.76,
          day_return_pct: -0.428283,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: false,
        },
      ],
    });

    expect(result.navSeries.map((point) => point.date)).toEqual([
      '2026-09-07',
      '2026-09-08',
      '2026-09-09',
    ]);
    // The seam row applies the finalized period's own return, not the +10.8%
    // level jump the stitched view shows between the two bases.
    expect(result.navSeries[1].returnPct).toBeCloseTo(-1.102422, 5);
    expect(result.navSeries[2].returnPct).toBeCloseTo(-1.526, 2);
  });

  it('forward-fills weekend gaps so the plotted series stays continuous (#4014)', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-04', nav: 100.886423, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-08', nav: 100.362022, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [],
      metrics: null,
      attribution: [],
      events: [],
    });

    expect(result.navSeries.map((point) => point.date)).toEqual([
      '2026-09-04',
      '2026-09-05',
      '2026-09-06',
      '2026-09-07',
      '2026-09-08',
    ]);
    expect(result.navSeries.slice(0, 4).map((point) => point.returnPct)).toEqual([0, 0, 0, 0]);
    expect(result.navSeries.at(-1)!.returnPct).toBeCloseTo(-0.5198, 3);
  });

  it('drops an implausible accounting step instead of drawing a cliff (#4014)', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-08-24', nav: 101.327006, cash_pct: 20, invested_pct: 80 },
        { date: '2026-08-25', nav: 3.35208926, cash_pct: 20, invested_pct: 80 },
        { date: '2026-08-26', nav: 15.13, cash_pct: 20, invested_pct: 80 },
        { date: '2026-08-27', nav: 102.477988, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [],
      metrics: null,
      attribution: [],
      events: [],
      accountingNav: [
        {
          date: '2026-08-24',
          nav: 101.327006,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: 0.2822,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
          series_seam: false,
        },
        {
          date: '2026-08-25',
          nav: 3.35208926,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: 3252.08926,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: true,
        },
        {
          date: '2026-08-26',
          nav: 15.13,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: 0,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: false,
        },
        {
          date: '2026-08-27',
          nav: 102.477988,
          cash_pct: 20,
          invested_pct: 80,
          day_return_pct: -0.436605,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: false,
        },
      ],
    });

    expect(result.navSeries.map((point) => point.date)).toEqual([
      '2026-08-24',
      '2026-08-25',
      '2026-08-26',
      '2026-08-27',
    ]);
    // The 0.10 → 3.35 opening period is a funding artifact, not a +3252% return.
    expect(result.navSeries.every((point) => Math.abs(point.returnPct) < 1)).toBe(true);
    expect(result.navSeries.map((point) => point.returnPct)).toEqual([
      0,
      0,
      0,
      -0.436605,
    ]);
  });

  it('draws per-asset contribution from daily realized attribution when marks are stale', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-08', nav: 110.74928206, cash_pct: 18.16, invested_pct: 81.84 },
        { date: '2026-09-09', nav: 110.27496181, cash_pct: 18.24, invested_pct: 81.76 },
        { date: '2026-09-10', nav: 109.6668758, cash_pct: 18.34, invested_pct: 81.66 },
      ],
      // Marks stop at the last enriched date; the realized view stays current.
      positions: [position('2026-09-10', 'AAA', 60), position('2026-09-10', 'BBB', 40)],
      metrics: null,
      attribution: [],
      events: [],
      realizedAttribution: [
        realized('2026-09-08', 'AAA', 0.1),
        realized('2026-09-08', 'BBB', 0.2),
        realized('2026-09-09', 'AAA', -0.3),
        realized('2026-09-09', 'BBB', 0.1),
        realized('2026-09-10', 'AAA', -0.2),
        realized('2026-09-10', 'BBB', -0.4),
      ],
    });

    expect(result.contributionSeries.map((point) => point.contributions.AAA)).toEqual([
      0, -0.3, -0.5,
    ]);
    expect(result.contributionSeries.map((point) => point.contributions.BBB)).toEqual([
      0, 0.1, -0.3,
    ]);
  });

  it('prefers realized daily attribution over weight-times-price marks', () => {
    const first = { ...position('2026-07-01', 'AAA', 20), current_price: 100 };
    const latest = { ...position('2026-07-17', 'AAA', 20), current_price: 110 };
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-07-01', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-17', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [first, latest],
      metrics,
      attribution: [],
      events: [],
      // Marks alone would produce [0, 2]; realized says +0.5.
      realizedAttribution: [realized('2026-07-01', 'AAA', 4), realized('2026-07-17', 'AAA', 0.5)],
    });

    expect(result.contributionSeries.map((point) => point.contributions.AAA)).toEqual([0, 0.5]);
  });

  it('keeps realized contribution keys scoped to the current book', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-09', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-10', nav: 101, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [position('2026-09-10', 'AAA', 100)],
      metrics: null,
      attribution: [],
      events: [],
      realizedAttribution: [
        realized('2026-09-09', 'AAA', 0.1),
        realized('2026-09-09', 'GONE', 9),
        realized('2026-09-10', 'AAA', 0.2),
        realized('2026-09-10', 'GONE', 9),
      ],
    });

    expect(Object.keys(result.contributionSeries[1].contributions)).toEqual(['AAA']);
  });

  it('falls back to weight-times-price marks when realized attribution is empty', () => {
    const first = { ...position('2026-07-01', 'AAA', 20), current_price: 100 };
    const latest = { ...position('2026-07-17', 'AAA', 20), current_price: 110 };
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-07-01', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-07-17', nav: 106, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [first, latest],
      metrics,
      attribution: [],
      events: [],
      realizedAttribution: [],
    });

    expect(result.contributionSeries.map((point) => point.contributions.AAA)).toEqual([0, 2]);
  });

  it('keeps pre-coverage days flat when the realized view starts mid-run', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-08', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-09', nav: 101, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-10', nav: 102, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [position('2026-09-10', 'AAA', 100)],
      metrics: null,
      attribution: [],
      events: [],
      realizedAttribution: [
        realized('2026-09-09', 'AAA', 0.4),
        realized('2026-09-10', 'AAA', 0.6),
      ],
    });

    // No finalized row for day one: the bar stays flat at the base rather than
    // switching back to the weight-times-mark series mid-window.
    expect(result.contributionSeries.map((point) => point.contributions.AAA)).toEqual([
      0, 0.4, 1,
    ]);
  });

  it('skips realized rows with a null contribution value', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-09', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-10', nav: 101, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [position('2026-09-10', 'AAA', 100)],
      metrics: null,
      attribution: [],
      events: [],
      realizedAttribution: [
        { ...realized('2026-09-09', 'AAA', 0), contribution_pct: null },
        realized('2026-09-10', 'AAA', 0.5),
      ],
    });

    expect(result.contributionSeries.map((point) => point.contributions.AAA)).toEqual([0, 0.5]);
  });

  it('falls back to marks when realized rows only cover dates outside the plotted run', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-05', nav: 99.92, cash_pct: 18, invested_pct: 82 },
        { date: '2026-09-08', nav: 110.74928206, cash_pct: 18.16, invested_pct: 81.84 },
        { date: '2026-09-09', nav: 110.27496181, cash_pct: 18.24, invested_pct: 81.76 },
        { date: '2026-09-10', nav: 109.6668758, cash_pct: 18.34, invested_pct: 81.66 },
      ],
      accountingNav: [
        {
          date: '2026-09-05',
          nav: 99.92,
          cash_pct: 18,
          invested_pct: 82,
          day_return_pct: null,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
          series_seam: false,
        },
        {
          date: '2026-09-08',
          nav: 110.74928206,
          cash_pct: 18.16,
          invested_pct: 81.84,
          day_return_pct: null,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: true,
        },
        {
          date: '2026-09-09',
          nav: 110.27496181,
          cash_pct: 18.24,
          invested_pct: 81.76,
          day_return_pct: null,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: false,
        },
        {
          date: '2026-09-10',
          nav: 109.6668758,
          cash_pct: 18.34,
          invested_pct: 81.66,
          day_return_pct: null,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          series_seam: false,
        },
      ],
      positions: [
        { ...position('2026-09-08', 'AAA', 100), current_price: 100 },
        { ...position('2026-09-10', 'AAA', 100), current_price: 110 },
      ],
      metrics: null,
      attribution: [],
      events: [],
      // The view stopped at the prior run: rows exist but none fall inside the
      // plotted post-seam window. A flat-zero realized series must not starve
      // the marks accrual (which prices AAA +10%).
      realizedAttribution: [
        realized('2026-09-04', 'AAA', 0.5),
        realized('2026-09-05', 'AAA', 0.5),
      ],
    });

    expect(result.navSeries.map((point) => point.date)).toEqual([
      '2026-09-05',
      '2026-09-06',
      '2026-09-07',
      '2026-09-08',
      '2026-09-09',
      '2026-09-10',
    ]);
    expect(result.contributionSeries.map((point) => point.contributions.AAA)).toEqual([
      0, 0, 0, 0, 0, 10,
    ]);
    expect(result.contributionSource).toBe('marks');
  });

  it('badges the marks fallback when the realized attribution read failed', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-09', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-10', nav: 101, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [position('2026-09-10', 'AAA', 100)],
      metrics: null,
      attribution: [],
      events: [],
      realizedAttribution: [],
      realizedAttributionDegraded: true,
    });

    expect(result.contributionSource).toBe('marks_degraded');
  });

  it('badges a truncated realized read even when rows were rendered', () => {
    const result = buildPerformanceTearsheet({
      nav: [
        { date: '2026-09-09', nav: 100, cash_pct: 20, invested_pct: 80 },
        { date: '2026-09-10', nav: 101, cash_pct: 20, invested_pct: 80 },
      ],
      positions: [position('2026-09-10', 'AAA', 100)],
      metrics: null,
      attribution: [],
      events: [],
      realizedAttribution: [realized('2026-09-10', 'AAA', 0.5)],
      realizedAttributionDegraded: true,
    });

    expect(result.contributionSource).toBe('realized_truncated');
  });
});
