/**
 * Self-contained tests for the dashboard-api performance kernel (`ssot.ts`).
 *
 * Expected values were verified byte-for-value against the client-side
 * originals (`apps/dashboard/lib/performance-ssot.ts`,
 * `apps/dashboard/lib/accounting-views.ts`, `apps/dashboard/lib/dashboard-ssot.ts`,
 * `apps/dashboard/lib/benchmark-tickers.ts`, `apps/dashboard/lib/brief-book-event.ts`,
 * `packages/ui` live-performance-kpis) with a scratch parity harness before
 * this file was committed — no workspace imports remain here on purpose
 * (the worker ships zero runtime dependencies).
 */
import { describe, expect, it } from 'vitest';

import {
  buildContinuityNavSeries,
  buildPerformanceSsotMeta,
  calendarDaysBetween,
  chainNavContinuity,
  committedBookDate,
  crossesNavSeam,
  currentNavRun,
  derivedDayReturnPct,
  eventWeightDeltaPp,
  findNavSeriesSeams,
  inceptionVsBenchmark,
  informationRatioFromDaily,
  isLiveMarksOverlay,
  isMaterialBookEvent,
  lagDirection,
  metricsDivergenceBadgeLabel,
  navContractBadgeLabel,
  navSeriesContractLabel,
  olsBeta,
  overlappingDailyReturns,
  periodReturnPct,
  persistedHeadlinesAgree,
  persistedHeadlinesFromNav,
  pickBenchmarkPoints,
  pickBriefBenchmarkTicker,
  resolveInvestedPct,
  selectBriefLedgerDayEvents,
  sinceInceptionPctFromNav,
  sortTickerUniverse,
  MIN_OVERLAP_DAYS,
  PERSISTED_KPI_TOLERANCE_PP,
} from './ssot';

const NAV6 = [
  { date: '2026-08-20', nav: 100, source: 'legacy_nav_history', contract: 'legacy_estimate' },
  {
    date: '2026-08-21',
    nav: 102,
    day_return_pct: 2,
    source: 'legacy_nav_history',
    contract: 'legacy_estimate',
  },
  {
    date: '2026-08-22',
    nav: 101,
    day_return_pct: null,
    source: 'legacy_nav_history',
    contract: 'legacy_estimate',
  },
  {
    date: '2026-08-26',
    nav: 200,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
    series_seam: true,
  },
  {
    date: '2026-08-27',
    nav: 202,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
  },
  {
    date: '2026-08-28',
    nav: 204.04,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
  },
];

const SPY6 = [
  { date: '2026-08-20', price: 500 },
  { date: '2026-08-21', price: 505 },
  { date: '2026-08-22', price: 502.5 },
  { date: '2026-08-26', price: 510 },
  { date: '2026-08-27', price: 512 },
  { date: '2026-08-28', price: 515 },
];

describe('calendar + book date', () => {
  it('counts signed UTC calendar days, null when malformed', () => {
    expect(calendarDaysBetween('2026-08-27', '2026-08-28')).toBe(1);
    expect(calendarDaysBetween('2026-08-28', '2026-08-27')).toBe(-1);
    expect(calendarDaysBetween('2026-08-28', '2026-08-28')).toBe(0);
    expect(calendarDaysBetween('not-a-date', '2026-08-28')).toBeNull();
  });
  it('committedBookDate never substitutes a newer position date', () => {
    expect(committedBookDate('2026-08-28', ['2026-08-20', '2026-08-28', '2026-08-29'])).toBe(
      '2026-08-28',
    );
    expect(committedBookDate('2026-08-28', ['2026-08-29'])).toBeNull();
    expect(committedBookDate(null, ['2026-08-28'])).toBeNull();
  });
});

describe('invested precedence', () => {
  it('prefers tip, then book weights, then metrics, then null', () => {
    expect(
      resolveInvestedPct({
        tipInvestedPct: 35.13,
        bookWeightInvestedPct: 30,
        metricsInvestedPct: 80,
      }),
    ).toEqual({ investedPct: 35.13, definition: 'accounting_nav_tip' });
    expect(
      resolveInvestedPct({
        tipInvestedPct: null,
        bookWeightInvestedPct: 30,
        metricsInvestedPct: 80,
      }),
    ).toEqual({ investedPct: 30, definition: 'book_weights' });
    expect(
      resolveInvestedPct({
        tipInvestedPct: null,
        bookWeightInvestedPct: null,
        metricsInvestedPct: 80,
      }),
    ).toEqual({ investedPct: 80, definition: 'portfolio_metrics' });
    expect(
      resolveInvestedPct({
        tipInvestedPct: null,
        bookWeightInvestedPct: null,
        metricsInvestedPct: null,
      }),
    ).toEqual({ investedPct: null, definition: 'unavailable' });
  });
});

describe('seam guard', () => {
  it('detects explicit and source-flip seams', () => {
    expect(crossesNavSeam(NAV6[3], NAV6[2])).toBe(true);
    expect(crossesNavSeam(NAV6[4], NAV6[3])).toBe(false);
    expect(crossesNavSeam(NAV6[1], null)).toBe(false);
  });
  it('nulls day return across seams and wide gaps, keeps stored values', () => {
    // Seam row with a stored return still refuses — phantom jumps never print.
    expect(derivedDayReturnPct({ ...NAV6[3], day_return_pct: 9.9 }, NAV6[2])).toBeNull();
    expect(derivedDayReturnPct(NAV6[1], NAV6[0])).toBe(2);
    // 6-day gap is a finalizer hole, not a session return.
    expect(
      derivedDayReturnPct(
        { date: '2026-08-28', nav: 110 },
        { date: '2026-08-22', nav: 100 },
      ),
    ).toBeNull();
    expect(derivedDayReturnPct(NAV6[5], NAV6[4])).toBeCloseTo(1.0099, 4);
  });
  it('finds seams and isolates the current run', () => {
    expect(findNavSeriesSeams(NAV6)).toEqual(['2026-08-26']);
    expect(currentNavRun(NAV6).map((r) => r.date)).toEqual([
      '2026-08-26',
      '2026-08-27',
      '2026-08-28',
    ]);
  });
});

describe('continuity chain', () => {
  it('chains runs onto base-100 without bridging the seam jump', () => {
    const chained = chainNavContinuity(NAV6);
    expect(chained[0]).toEqual({ date: '2026-08-20', nav: 100 });
    expect(chained[3]).toEqual({ date: '2026-08-26', nav: 101 });
    expect(chained.at(-1)!.nav).toBeCloseTo(103.0402, 4);
  });
  it('forward-fills weekend gaps flat and rounds to 6dp', () => {
    const series = buildContinuityNavSeries(NAV6);
    expect(series.map((p) => p.date)).toEqual([
      '2026-08-20',
      '2026-08-21',
      '2026-08-22',
      '2026-08-23',
      '2026-08-24',
      '2026-08-25',
      '2026-08-26',
      '2026-08-27',
      '2026-08-28',
    ]);
    expect(series[3]).toEqual({ date: '2026-08-23', nav: 101, returnPct: 1 });
    expect(series.at(-1)).toEqual({ date: '2026-08-28', nav: 103.0402, returnPct: 3.0402 });
  });
  it('periodReturnPct needs two positive points', () => {
    expect(periodReturnPct([100, 103.0402])).toBe(3.0402);
    expect(periodReturnPct([100])).toBeNull();
    expect(periodReturnPct([])).toBeNull();
  });
});

describe('persisted headlines + ssot meta', () => {
  it('derives since-% from the chained series and guards the tip', () => {
    const headlines = persistedHeadlinesFromNav(NAV6, {
      bookWeightInvestedPct: 35.13,
      metricsInvestedPct: 80,
    });
    expect(headlines.sinceInceptionPct).toBeCloseTo(3.0402, 4);
    expect(headlines.sinceInceptionStartDate).toBe('2026-08-20');
    expect(headlines.dayReturnPct).toBeCloseTo(1.0099, 4);
    expect(headlines.navAsOf).toBe('2026-08-28');
    expect(headlines.investedPct).toBe(35.13);
    expect(headlines.investedDefinition).toBe('book_weights');
  });
  it('builds ssot meta with signed lag and unstamped marks', () => {
    const meta = buildPerformanceSsotMeta({
      navRows: NAV6,
      metricsAsOf: '2026-08-27',
      snapshotDate: '2026-08-28',
      positionDates: ['2026-08-28'],
      positionMetricsAsOf: ['2026-08-27', null],
      bookWeightInvestedPct: 35.13,
      metricsInvestedPct: 80,
    });
    expect(meta.navContract).toBe('finalized_accounting');
    expect(meta.navAsOf).toBe('2026-08-28');
    expect(meta.metricsAsOf).toBe('2026-08-27');
    expect(meta.metricsLagDays).toBe(1);
    expect(meta.metricsLagging).toBe(true);
    expect(meta.bookAsOf).toBe('2026-08-28');
    expect(meta.marksUnstamped).toBe(true);
    expect(meta.tipDayReturnPct).toBeCloseTo(1.0099, 4);
  });
  it('badges symmetric lag directions and contract copy', () => {
    expect(metricsDivergenceBadgeLabel({ metricsLagging: true, metricsLagDays: 1 })).toBe(
      'metrics lag',
    );
    expect(metricsDivergenceBadgeLabel({ metricsLagging: true, metricsLagDays: -2 })).toBe(
      'nav lag',
    );
    expect(metricsDivergenceBadgeLabel({ metricsLagging: false, metricsLagDays: 0 })).toBeNull();
    expect(lagDirection(1)).toBe('metrics lag');
    expect(lagDirection(-1)).toBe('nav lag');
    expect(lagDirection(0)).toBeNull();
    expect(lagDirection(null)).toBeNull();
    expect(navContractBadgeLabel('finalized_accounting')).toBe('finalized accounting');
    expect(navContractBadgeLabel('legacy_estimate')).toBe('legacy estimate');
    expect(navContractBadgeLabel('empty')).toBe('no nav series');
    expect(navSeriesContractLabel([])).toBe('empty');
  });
  it('headline agreement uses the 0.05pp tolerance', () => {
    expect(persistedHeadlinesAgree(8.4, 8.42)).toBe(true);
    expect(persistedHeadlinesAgree(8.4, 8.46)).toBe(false);
    expect(persistedHeadlinesAgree(null, 8.4)).toBe(false);
    expect(PERSISTED_KPI_TOLERANCE_PP).toBe(0.05);
  });
});

describe('overlap-gated relative metrics', () => {
  it('clips benchmark points to the window', () => {
    expect(pickBenchmarkPoints(SPY6, '2026-08-20', '2026-08-28')).toEqual({
      start: { date: '2026-08-20', price: 500 },
      end: { date: '2026-08-28', price: 515 },
    });
    expect(pickBenchmarkPoints(SPY6, '2026-09-01', '2026-09-02')).toBeNull();
  });
  it('nulls beta/IR below the 20-pair floor, never invents them', () => {
    expect(MIN_OVERLAP_DAYS).toBe(20);
    const { port, bench } = overlappingDailyReturns(
      NAV6.map((r) => ({ date: r.date, nav: r.nav })),
      SPY6,
    );
    expect(port).toHaveLength(5);
    expect(olsBeta(port, bench)).toBeNull();
    expect(informationRatioFromDaily(port, bench)).toBeNull();
  });
  it('estimates beta on a real sample (bench = half the port move → β ≈ 2)', () => {
    const port = Array.from({ length: 25 }, (_, i) => (i % 2 === 0 ? 0.01 : -0.005));
    const bench = port.map((r) => r / 2);
    expect(olsBeta(port, bench)).toBeCloseTo(2, 6);
    expect(informationRatioFromDaily(port, bench)).not.toBeNull();
  });
  it('since-inception signs off a base-100 anchor', () => {
    expect(sinceInceptionPctFromNav(100, 103.0402)).toBeCloseTo(3.0402, 4);
    expect(sinceInceptionPctFromNav(0, 100)).toBeNull();
  });
  it('aligns portfolio vs benchmark over the chained window', () => {
    const blurb = inceptionVsBenchmark(NAV6, { SPY: SPY6 });
    expect(blurb?.ticker).toBe('SPY');
    expect(blurb?.portPct).toBeCloseTo(3.0402, 4);
    expect(blurb?.benchPct).toBeCloseTo(3, 4);
    expect(blurb?.excessPct).toBeCloseTo(0.0402, 3);
  });
});

describe('overlay gate + tickers + ledger events', () => {
  it('overlay engages only on a nonzero move', () => {
    expect(isLiveMarksOverlay(0.4)).toBe(true);
    expect(isLiveMarksOverlay(0)).toBe(false);
    expect(isLiveMarksOverlay(null)).toBe(false);
    expect(isLiveMarksOverlay(undefined)).toBe(false);
  });
  it('picks SPY first, then universe order', () => {
    expect(
      pickBriefBenchmarkTicker({ SPY: { history: [{ date: 'd', price: 1 }] } }),
    ).toBe('SPY');
    expect(pickBriefBenchmarkTicker({ QQQ: { history: [{ date: 'd', price: 1 }] } })).toBe('QQQ');
    expect(pickBriefBenchmarkTicker({})).toBeNull();
    expect(sortTickerUniverse(['qqq', 'spy', 'zzz'])).toEqual(['SPY', 'QQQ', 'ZZZ']);
  });
  it('keeps material day moves only, largest first, never an older day', () => {
    const events = [
      { date: '2026-08-28', ticker: 'XLV', event: 'TRIM', weight_pct: 4.9, prev_weight_pct: 9.9 },
      { date: '2026-08-28', ticker: 'DBO', event: 'ADD', weight_pct: 5.0, prev_weight_pct: 5.0 },
      { date: '2026-08-28', ticker: 'EWZ', event: 'HOLD', weight_pct: 5, prev_weight_pct: 5 },
      { date: '2026-08-27', ticker: 'XLF', event: 'EXIT', weight_pct: 0, prev_weight_pct: 3 },
    ];
    expect(eventWeightDeltaPp(events[0])).toBeCloseTo(-5, 6);
    expect(isMaterialBookEvent(events[0])).toBe(true);
    expect(isMaterialBookEvent(events[1])).toBe(false);
    expect(isMaterialBookEvent(events[2])).toBe(false);
    const day = selectBriefLedgerDayEvents(events, '2026-08-28');
    expect(day.map((e) => e.ticker)).toEqual(['XLV']);
    expect(selectBriefLedgerDayEvents(events, null)).toEqual([]);
  });
});
