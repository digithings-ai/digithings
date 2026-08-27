import { describe, expect, it } from 'vitest';
import {
  computeLivePerformanceKpis,
  computeLiveVsMarkPct,
  derivePriceAsOfDate,
  type LiveKpiPosition,
} from './live-performance-kpis';

const positions: LiveKpiPosition[] = [
  {
    ticker: 'SPY',
    weightPct: 60,
    markPrice: 500,
    effectivePrice: 510,
    isLive: true,
    metricsAsOf: '2026-08-26',
    livePriceDate: '2026-08-27',
  },
  {
    ticker: 'TLT',
    weightPct: 30,
    markPrice: 90,
    effectivePrice: 90,
    isLive: false,
    metricsAsOf: '2026-08-26',
    livePriceDate: null,
  },
  {
    ticker: 'CASH',
    weightPct: 10,
    markPrice: null,
    effectivePrice: null,
    isLive: false,
    metricsAsOf: '2026-08-26',
    livePriceDate: null,
  },
];

describe('computeLiveVsMarkPct', () => {
  it('weights live legs only — stale marks contribute flat', () => {
    // SPY: 60% * (510/500 - 1) = 1.2%
    expect(computeLiveVsMarkPct(positions)).toBeCloseTo(1.2, 4);
  });
});

describe('derivePriceAsOfDate', () => {
  it('prefers live quote date over book mark date', () => {
    expect(derivePriceAsOfDate(positions)).toBe('2026-08-27');
  });

  it('falls back to latest metrics_as_of when nothing is live', () => {
    const stale = positions.map((p) => ({ ...p, isLive: false, livePriceDate: null }));
    expect(derivePriceAsOfDate(stale)).toBe('2026-08-26');
  });
});

describe('computeLivePerformanceKpis', () => {
  const navHistory = [
    { date: '2026-06-23', nav: 100 },
    { date: '2026-08-25', nav: 102 },
    { date: '2026-08-26', nav: 103 },
  ];

  const benchmarkHistory = [
    { date: '2026-06-23', price: 500 },
    { date: '2026-08-26', price: 520 },
  ];

  it('computes live NAV from accounting anchor + live move', () => {
    const kpis = computeLivePerformanceKpis({
      positions,
      navHistory,
      benchmarkHistory,
      benchmarkTicker: 'SPY',
    });
    // liveVsMarkPct ≈ 1.2 → liveNav ≈ 103 * 1.012 = 104.236
    expect(kpis.liveNav).toBeCloseTo(104.236, 2);
    expect(kpis.priceAsOfDate).toBe('2026-08-27');
    expect(kpis.bookNavDate).toBe('2026-08-26');
  });

  it('computes day return vs prior accounting NAV row', () => {
    const kpis = computeLivePerformanceKpis({
      positions,
      navHistory,
      benchmarkHistory,
      benchmarkTicker: 'SPY',
    });
    expect(kpis.dayReturnPct).toBeCloseTo(((104.236 / 102 - 1) * 100), 1);
  });

  it('computes since-inception on base-100 index', () => {
    const kpis = computeLivePerformanceKpis({
      positions,
      navHistory,
      benchmarkHistory,
      benchmarkTicker: 'SPY',
    });
    expect(kpis.sinceInceptionPct).toBeCloseTo(104.236 - 100, 2);
    expect(kpis.sinceInceptionStartDate).toBe('2026-06-23');
  });

  it('computes excess return vs aligned benchmark window', () => {
    const kpis = computeLivePerformanceKpis({
      positions,
      navHistory,
      benchmarkHistory,
      benchmarkTicker: 'SPY',
    });
    const portPct = (104.236 / 100 - 1) * 100;
    const benchPct = (520 / 500 - 1) * 100;
    expect(kpis.excessReturnPct).toBeCloseTo(portPct - benchPct, 1);
    expect(kpis.benchmarkTicker).toBe('SPY');
  });

  it('returns null KPIs when NAV history is empty', () => {
    const kpis = computeLivePerformanceKpis({ positions, navHistory: [] });
    expect(kpis.liveNav).toBeNull();
    expect(kpis.dayReturnPct).toBeNull();
    expect(kpis.sinceInceptionPct).toBeNull();
    expect(kpis.excessReturnPct).toBeNull();
  });
});
