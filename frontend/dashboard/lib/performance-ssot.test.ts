import { describe, expect, it } from 'vitest';
import { buildPerformanceTearsheet } from './observability-queries';
import {
  buildPerformanceSsotMeta,
  isLiveMarksOverlay,
  persistedHeadlinesAgree,
  persistedHeadlinesFromNav,
  resolveInvestedPct,
} from './performance-ssot';

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
});
