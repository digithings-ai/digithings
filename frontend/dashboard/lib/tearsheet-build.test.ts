import { describe, expect, it } from 'vitest';
import { buildPerformanceTearsheet } from './observability-queries';
import type { TableRow } from './database.types';

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
    expect(result.metricsAsOf).toBe('2026-07-17');
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
});
