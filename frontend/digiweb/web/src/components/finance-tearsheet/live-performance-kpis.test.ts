import { describe, expect, it } from 'vitest';
import {
  computeLivePerformanceKpis,
  computeLiveVsMarkPct,
  dayReturnAnchorNav,
  derivePriceAsOfDate,
  inceptionSignAgreesWithBase100,
  MIN_OVERLAP_DAYS,
  sinceInceptionPctFromNav,
  type LiveKpiPosition,
} from './live-performance-kpis';

/** Weekday series long enough for Jensen α / IR (≥ {@link MIN_OVERLAP_DAYS} pairs). */
function buildAlignedSeries(days: number): {
  navHistory: Array<{ date: string; nav: number }>;
  benchmarkHistory: Array<{ date: string; price: number }>;
} {
  const navHistory: Array<{ date: string; nav: number }> = [];
  const benchmarkHistory: Array<{ date: string; price: number }> = [];
  let nav = 100;
  let price = 500;
  const start = Date.UTC(2026, 5, 1); // 2026-06-01
  for (let i = 0; i < days; i++) {
    const d = new Date(start + i * 86_400_000);
    // Skip weekends so we mimic trading-day cadence without calendar deps.
    if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
    const date = d.toISOString().slice(0, 10);
    nav *= 1 + 0.001 + (i % 5) * 0.0002;
    price *= 1 + 0.0005 + (i % 7) * 0.0001;
    navHistory.push({ date, nav });
    benchmarkHistory.push({ date, price });
  }
  return { navHistory, benchmarkHistory };
}

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

  it('does not shrink the benchmark window when metrics_as_of is older than book NAV', () => {
    const staleMarks = positions.map((p) => ({
      ...p,
      isLive: false,
      livePriceDate: null,
      metricsAsOf: '2026-08-20',
    }));
    const kpis = computeLivePerformanceKpis({
      positions: staleMarks,
      navHistory: [
        { date: '2026-06-23', nav: 100 },
        { date: '2026-08-26', nav: 103 },
      ],
      benchmarkHistory: [
        { date: '2026-06-23', price: 500 },
        { date: '2026-08-20', price: 510 },
        { date: '2026-08-26', price: 520 },
      ],
      benchmarkTicker: 'SPY',
    });
    // Book is 2026-08-26; stale mark date must not win the endDate pick.
    expect(kpis.bookNavDate).toBe('2026-08-26');
    expect(kpis.priceAsOfDate).toBe('2026-08-20');
    expect(kpis.benchmarkReturnPct).toBeCloseTo((520 / 500 - 1) * 100, 6);
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

  it('computes non-null excess, alpha, and IR when NAV + SPY share enough overlap', () => {
    const { navHistory: longNav, benchmarkHistory: spy } = buildAlignedSeries(45);
    expect(longNav.length).toBeGreaterThan(MIN_OVERLAP_DAYS + 1);
    const kpis = computeLivePerformanceKpis({
      positions: positions.map((p) => ({
        ...p,
        isLive: false,
        livePriceDate: null,
        metricsAsOf: longNav[longNav.length - 1]!.date,
      })),
      navHistory: longNav,
      benchmarkHistory: spy,
      benchmarkTicker: 'SPY',
    });
    expect(kpis.benchmarkTicker).toBe('SPY');
    expect(kpis.excessReturnPct).not.toBeNull();
    expect(Number.isFinite(kpis.excessReturnPct)).toBe(true);
    expect(kpis.alphaPct).not.toBeNull();
    expect(Number.isFinite(kpis.alphaPct)).toBe(true);
    expect(kpis.informationRatio).not.toBeNull();
    expect(Number.isFinite(kpis.informationRatio)).toBe(true);
  });

  it('fails closed on alpha/IR when overlap is under MIN_OVERLAP_DAYS (excess still ok)', () => {
    const shortNav = [
      { date: '2026-06-23', nav: 100 },
      { date: '2026-06-24', nav: 101 },
      { date: '2026-06-25', nav: 102 },
    ];
    const shortSpy = [
      { date: '2026-06-23', price: 500 },
      { date: '2026-06-24', price: 505 },
      { date: '2026-06-25', price: 510 },
    ];
    const kpis = computeLivePerformanceKpis({
      positions: positions.map((p) => ({
        ...p,
        isLive: false,
        livePriceDate: null,
        metricsAsOf: '2026-06-25',
      })),
      navHistory: shortNav,
      benchmarkHistory: shortSpy,
      benchmarkTicker: 'SPY',
    });
    expect(kpis.excessReturnPct).not.toBeNull();
    expect(kpis.alphaPct).toBeNull();
    expect(kpis.informationRatio).toBeNull();
  });

  it('fails closed on excess/alpha when SPY series is missing', () => {
    const kpis = computeLivePerformanceKpis({
      positions,
      navHistory,
      benchmarkTicker: 'SPY',
    });
    expect(kpis.excessReturnPct).toBeNull();
    expect(kpis.alphaPct).toBeNull();
    expect(kpis.informationRatio).toBeNull();
  });
});
