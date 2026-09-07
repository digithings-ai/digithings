import { describe, expect, it } from 'vitest';
import { MIN_OVERLAP_DAYS } from '@digithings/web';
import { buildPerformanceTearsheet } from './observability-queries';
import {
  MAX_DAY_RETURN_GAP_DAYS,
  buildPerformanceSsotMeta,
  isLiveMarksOverlay,
  metricsDivergenceBadgeLabel,
  navContractBadgeLabel,
  persistedHeadlinesAgree,
  persistedHeadlinesFromNav,
  persistedInsightMetrics,
  performanceFreshnessNote,
  resolveInvestedPct,
} from './performance-ssot';

function weekdaySeries(
  count: number,
  startIso = '2026-06-01'
): Array<{ date: string; nav: number; price: number }> {
  const out: Array<{ date: string; nav: number; price: number }> = [];
  let nav = 100;
  let price = 500;
  const start = Date.parse(`${startIso}T00:00:00Z`);
  for (let i = 0; out.length < count; i++) {
    const d = new Date(start + i * 86_400_000);
    if (d.getUTCDay() === 0 || d.getUTCDay() === 6) continue;
    nav *= 1 + 0.001 + (out.length % 5) * 0.0003;
    price *= 1 + 0.0005 + (out.length % 7) * 0.0002;
    out.push({ date: d.toISOString().slice(0, 10), nav, price });
  }
  return out;
}

describe('performance SSOT (#3580)', () => {
  it('prefers accounting NAV tip invested % over stale portfolio_metrics', () => {
    const resolved = resolveInvestedPct({
      tipInvestedPct: 40.5,
      bookWeightInvestedPct: 41,
      metricsInvestedPct: 79,
    });
    expect(resolved.definition).toBe('accounting_nav_tip');
    expect(resolved.investedPct).toBe(40.5);
  });

  it('Brief persisted since-% agrees with Tearsheet net return when live overlay is off', () => {
    const nav = [
      {
        date: '2026-08-25',
        nav: 100,
        invested_pct: 80,
        day_return_pct: 0,
        source: 'legacy_nav_history',
        contract: 'legacy_estimate',
      },
      {
        date: '2026-09-03',
        nav: 99.426595,
        invested_pct: 45,
        day_return_pct: 0,
        source: 'legacy_nav_history',
        contract: 'legacy_estimate',
      },
      {
        date: '2026-09-04',
        nav: 99.426595,
        invested_pct: 40.5,
        day_return_pct: 0,
        source: 'legacy_nav_history',
        contract: 'legacy_estimate',
      },
    ];
    const brief = persistedHeadlinesFromNav(nav);
    const tearsheet = buildPerformanceTearsheet({
      nav: nav.map((row) => ({
        date: row.date,
        nav: row.nav,
        cash_pct: 100 - row.invested_pct,
        invested_pct: row.invested_pct,
      })),
      positions: [],
      metrics: null,
      attribution: [],
      accountingNav: nav.map((row) => ({
        ...row,
        cash_pct: 100 - row.invested_pct,
      })),
    });
    expect(persistedHeadlinesAgree(brief.sinceInceptionPct, tearsheet.netReturnPct)).toBe(true);
    expect(brief.investedPct).toBe(40.5);
    expect(tearsheet.navContract).toBe('legacy_estimate');
    expect(tearsheet.tipInvestedPct).toBe(40.5);
  });

  it('flags metrics lag when portfolio_metrics trails the NAV tip by ≥1 day', () => {
    const meta = buildPerformanceSsotMeta({
      navRows: [
        {
          date: '2026-09-04',
          nav: 99.4,
          invested_pct: 40.5,
          day_return_pct: 0,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
        },
      ],
      metricsAsOf: '2026-09-01',
      snapshotDate: '2026-09-04',
      positionDates: ['2026-09-04', '2026-09-03'],
      positionMetricsAsOf: [null, null],
      metricsInvestedPct: 79,
    });
    expect(meta.metricsLagging).toBe(true);
    expect(meta.metricsLagDays).toBe(3);
    expect(metricsDivergenceBadgeLabel(meta)).toBe('metrics lag');
    expect(meta.marksUnstamped).toBe(true);
    expect(meta.bookAsOf).toBe('2026-09-04');
    expect(meta.navContract).toBe('legacy_estimate');
    expect(meta.investedDefinition).toBe('accounting_nav_tip');
  });

  it('treats zero liveVsMarkPct as no live overlay', () => {
    expect(isLiveMarksOverlay(0)).toBe(false);
    expect(isLiveMarksOverlay(null)).toBe(false);
    expect(isLiveMarksOverlay(0.12)).toBe(true);
  });

  it('returns null since-inception for a single NAV row (matches Tearsheet)', () => {
    const brief = persistedHeadlinesFromNav([
      { date: '2026-09-04', nav: 99.4, invested_pct: 40.5 },
    ]);
    const tearsheet = buildPerformanceTearsheet({
      nav: [{ date: '2026-09-04', nav: 99.4, cash_pct: 59.5, invested_pct: 40.5 }],
      positions: [],
      metrics: null,
      attribution: [],
    });
    expect(brief.sinceInceptionPct).toBeNull();
    expect(tearsheet.netReturnPct).toBeNull();
  });

  it('ignores CASH when deciding marksUnstamped', () => {
    const meta = buildPerformanceSsotMeta({
      navRows: [
        {
          date: '2026-09-04',
          nav: 99.4,
          invested_pct: 40.5,
          day_return_pct: 0,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
        },
      ],
      metricsAsOf: '2026-09-04',
      snapshotDate: '2026-09-04',
      positionDates: ['2026-09-04'],
      positionMetricsAsOf: ['2026-09-04'], // equities stamped; CASH excluded by caller
    });
    expect(meta.marksUnstamped).toBe(false);
  });

  it('does not label a legacy-estimate tip as finalized accounting when history is mixed', () => {
    const meta = buildPerformanceSsotMeta({
      navRows: [
        {
          date: '2026-08-01',
          nav: 100,
          invested_pct: 80,
          day_return_pct: 0.1,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
        },
        {
          date: '2026-09-04',
          nav: 99.4,
          invested_pct: 40.5,
          day_return_pct: null,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
        },
      ],
      metricsAsOf: '2026-09-04',
      snapshotDate: '2026-09-04',
      positionDates: ['2026-09-04'],
      positionMetricsAsOf: ['2026-09-04'],
    });
    expect(meta.navContract).toBe('legacy_estimate');
    expect(navContractBadgeLabel(meta.navContract)).toBe('legacy estimate');
    expect(navContractBadgeLabel('finalized_accounting')).toBe('finalized accounting');
    expect(performanceFreshnessNote(meta)).toMatch(/legacy estimate/);
  });

  it('detects equal-magnitude NAV-behind-metrics divergence (finalizer stall)', () => {
    const meta = buildPerformanceSsotMeta({
      navRows: [
        {
          date: '2026-09-02',
          nav: 99.4,
          invested_pct: 40.5,
          day_return_pct: 0,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
        },
      ],
      metricsAsOf: '2026-09-04',
      snapshotDate: '2026-09-02',
      positionDates: ['2026-09-02'],
      positionMetricsAsOf: ['2026-09-02'],
    });
    expect(meta.metricsLagDays).toBe(-2);
    expect(meta.metricsLagging).toBe(true);
    expect(metricsDivergenceBadgeLabel(meta)).toBe('nav lag');
    expect(performanceFreshnessNote(meta)).toMatch(/nav tip 2026-09-02/);
  });

  it(`does not invent a session day return across a gap wider than ${MAX_DAY_RETURN_GAP_DAYS} days`, () => {
    const brief = persistedHeadlinesFromNav([
      { date: '2026-08-21', nav: 100, invested_pct: 80, day_return_pct: null },
      { date: '2026-09-04', nav: 104.5, invested_pct: 40.5, day_return_pct: null },
    ]);
    expect(brief.dayReturnPct).toBeNull();
  });

  it('derives day return across a weekend-sized adjacent gap when the tip omits day_return_pct', () => {
    const brief = persistedHeadlinesFromNav([
      { date: '2026-09-03', nav: 100, invested_pct: 40, day_return_pct: null },
      { date: '2026-09-04', nav: 101, invested_pct: 40, day_return_pct: null },
    ]);
    expect(brief.dayReturnPct).toBeCloseTo(1, 6);
  });

  it('does not clamp an accounting-tip invested % over 100', () => {
    const resolved = resolveInvestedPct({
      tipInvestedPct: 137,
      bookWeightInvestedPct: 40,
      metricsInvestedPct: 79,
    });
    expect(resolved.definition).toBe('accounting_nav_tip');
    expect(resolved.investedPct).toBe(137);
  });

  it('treats an empty open book as unstamped so as-of chrome stays caveated', () => {
    const meta = buildPerformanceSsotMeta({
      navRows: [
        {
          date: '2026-09-04',
          nav: 99.4,
          invested_pct: 40.5,
          day_return_pct: 0,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
        },
      ],
      metricsAsOf: '2026-09-04',
      snapshotDate: '2026-09-04',
      positionDates: [],
      positionMetricsAsOf: [],
    });
    expect(meta.marksUnstamped).toBe(true);
  });

  it('keeps alpha/IR when NAV/benchmark overlap meets MIN_OVERLAP_DAYS on a sparse (paginated) bench', () => {
    const series = weekdaySeries(MIN_OVERLAP_DAYS + 8);
    const nav = series.map((p) => ({ date: p.date, nav: p.nav }));
    const sparseBench = series.filter((_, i) => i % 3 === 0).map((p) => ({ date: p.date, price: p.price }));
    const insights = persistedInsightMetrics(nav, sparseBench);
    expect(insights.excessReturnPct).not.toBeNull();
    expect(insights.alphaPct).not.toBeNull();
    expect(insights.informationRatio).not.toBeNull();
  });

  it('keeps alpha/IR when paginated bench drops early dates but remaining overlap is valid', () => {
    const series = weekdaySeries(MIN_OVERLAP_DAYS + 12);
    const nav = series.map((p) => ({ date: p.date, nav: p.nav }));
    const lateBench = series.slice(8).map((p) => ({ date: p.date, price: p.price }));
    const insights = persistedInsightMetrics(nav, lateBench);
    expect(lateBench.length).toBeGreaterThan(MIN_OVERLAP_DAYS);
    expect(insights.alphaPct).not.toBeNull();
    expect(insights.informationRatio).not.toBeNull();
  });

  it('fails closed on alpha/IR when remaining overlap is under MIN_OVERLAP_DAYS', () => {
    const series = weekdaySeries(12);
    const insights = persistedInsightMetrics(
      series.map((p) => ({ date: p.date, nav: p.nav })),
      series.map((p) => ({ date: p.date, price: p.price }))
    );
    expect(insights.excessReturnPct).not.toBeNull();
    expect(insights.alphaPct).toBeNull();
    expect(insights.informationRatio).toBeNull();
  });

  it('surfaces tip cash % from the accounting NAV tip', () => {
    const meta = buildPerformanceSsotMeta({
      navRows: [
        {
          date: '2026-09-04',
          nav: 99.4,
          cash_pct: 59.5,
          invested_pct: 40.5,
          day_return_pct: 0,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
        },
      ],
      metricsAsOf: '2026-09-04',
      snapshotDate: '2026-09-04',
      positionDates: ['2026-09-04'],
      positionMetricsAsOf: ['2026-09-04'],
    });
    expect(meta.tipCashPct).toBe(59.5);
    expect(meta.tipInvestedPct).toBe(40.5);
  });
});
