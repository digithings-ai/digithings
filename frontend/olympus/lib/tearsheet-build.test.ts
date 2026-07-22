import { describe, expect, it } from 'vitest';
import { buildOlympusTearsheet } from './observability-queries';
import type { TableRow } from './database.types';

const position = (date: string, ticker: string, weight: number): TableRow<'positions'> =>
  ({
    id: `${date}-${ticker}`,
    date,
    ticker,
    name: ticker,
    category: 'equity_broad',
    weight_pct: weight,
    thesis_id: null,
    rationale: null,
    current_price: null,
    entry_price: null,
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

describe('buildOlympusTearsheet', () => {
  it('passes persisted headline returns through without deriving them from NAV', () => {
    const result = buildOlympusTearsheet({
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
    const result = buildOlympusTearsheet({
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

  it('derives only missing cumulative returns from the exact live history window', () => {
    const result = buildOlympusTearsheet({
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

    expect(result.netReturnPct).toBe(7);
    expect(result.benchmarkReturnPct).toBe(2);
    expect(result.relativeReturnPct).toBe(5);
    expect(result.returnsSource).toBe('mixed');
    expect(result.metricsAsOf).toBe('2026-07-17');
  });

  it('uses a clearly labeled live fallback when no persisted metrics row exists', () => {
    const result = buildOlympusTearsheet({
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
    const result = buildOlympusTearsheet({
      nav: [],
      positions: [position('2026-07-17', 'AAA', 20)],
      metrics,
      attribution: [
        attribution('2026-07-17', 'AAA', 1),
        attribution('2026-07-01', 'AAA', 0.5),
        attribution('2026-06-20', 'OLD', -0.2),
        attribution('2026-06-10', 'OLD', 0.1),
      ],
      events: [exitEvent('2026-06-21', 'OLD', -3.5)],
    });

    expect(result.currentHoldings.map((row) => row.ticker)).toEqual(['AAA']);
    expect(result.currentHoldings[0].attributionDate).toBe('2026-07-17');
    expect(result.historicalHoldings.map((row) => row.ticker)).toEqual(['OLD']);
    expect(result.historicalHoldings[0].attributionDate).toBe('2026-06-21');
    expect(result.historicalHoldings[0].realizedReturnPct).toBe(-3.5);
  });

  it('keeps current holdings visible when their attribution row is missing', () => {
    const result = buildOlympusTearsheet({
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
      attributionDate: null,
    });
  });
});
