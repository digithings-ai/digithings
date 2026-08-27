import { describe, expect, it } from 'vitest';
import {
  computeLivePerformanceKpis,
  computeLiveVsMarkPct,
  dayReturnAnchorNav,
  derivePriceAsOfDate,
  inceptionSignAgreesWithBase100,
  sinceInceptionPctFromNav,
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

describe('sinceInceptionPctFromNav + base-100 sign invariant', () => {
  it('agrees with liveNav − 100 when seeded at 100', () => {
    expect(sinceInceptionPctFromNav(100, 104.236)).toBeCloseTo(4.236, 3);
    expect(sinceInceptionPctFromNav(100, 98.5)).toBeCloseTo(-1.5, 6);
  });

  it('fails the invariant when a positive % is paired with NAV under 100', () => {
    expect(inceptionSignAgreesWithBase100(100, 98.5, -1.5)).toBe(true);
    expect(inceptionSignAgreesWithBase100(100, 98.5, 1.2)).toBe(false);
    expect(inceptionSignAgreesWithBase100(100, 104, 4)).toBe(true);
    expect(inceptionSignAgreesWithBase100(100, 104, -1)).toBe(false);
  });
});

describe('dayReturnAnchorNav', () => {
  const nav = [
    { date: '2026-08-25', nav: 102 },
    { date: '2026-08-26', nav: 103 },
  ];

  it('uses latest close when price marks are on a later calendar day', () => {
    expect(dayReturnAnchorNav(nav, '2026-08-27')).toBe(103);
  });

  it('uses prior close when marks share the book date (post-EOD)', () => {
    expect(dayReturnAnchorNav(nav, '2026-08-26')).toBe(102);
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

  it('computes day return vs latest accounting close when marking a new day', () => {
    const kpis = computeLivePerformanceKpis({
      positions,
      navHistory,
      benchmarkHistory,
      benchmarkTicker: 'SPY',
    });
    // priceAsOf 2026-08-27 > book 2026-08-26 → anchor = 103 (not 102)
    expect(kpis.dayReturnPct).toBeCloseTo((104.236 / 103 - 1) * 100, 1);
    expect(kpis.dayReturnPct).toBeCloseTo(1.2, 1);
  });

  it('computes since-inception on base-100 index with matching sign', () => {
    const kpis = computeLivePerformanceKpis({
      positions,
      navHistory,
      benchmarkHistory,
      benchmarkTicker: 'SPY',
    });
    expect(kpis.sinceInceptionPct).toBeCloseTo(104.236 - 100, 2);
    expect(kpis.sinceInceptionStartDate).toBe('2026-06-23');
    expect(
      inceptionSignAgreesWithBase100(100, kpis.liveNav!, kpis.sinceInceptionPct!)
    ).toBe(true);
  });

  it('never reports positive since-inception when live NAV is under 100', () => {
    const kpis = computeLivePerformanceKpis({
      positions: positions.map((p) => ({ ...p, isLive: false, livePriceDate: null })),
      navHistory: [
        { date: '2026-06-23', nav: 100 },
        { date: '2026-08-26', nav: 98.5 },
      ],
    });
    expect(kpis.liveNav).toBeCloseTo(98.5, 4);
    expect(kpis.sinceInceptionPct).toBeLessThan(0);
    expect(
      inceptionSignAgreesWithBase100(100, kpis.liveNav!, kpis.sinceInceptionPct!)
    ).toBe(true);
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
    expect(kpis.relativeGainPct).toBeCloseTo(kpis.excessReturnPct!, 6);
    expect(kpis.benchmarkTicker).toBe('SPY');
    expect(kpis.portfolioReturnPct).toBeCloseTo(portPct, 1);
    expect(kpis.benchmarkReturnPct).toBeCloseTo(benchPct, 1);
  });

  it('returns null KPIs when NAV history is empty', () => {
    const kpis = computeLivePerformanceKpis({ positions, navHistory: [] });
    expect(kpis.liveNav).toBeNull();
    expect(kpis.dayReturnPct).toBeNull();
    expect(kpis.sinceInceptionPct).toBeNull();
    expect(kpis.excessReturnPct).toBeNull();
    expect(kpis.alphaPct).toBeNull();
    expect(kpis.informationRatio).toBeNull();
  });
});
