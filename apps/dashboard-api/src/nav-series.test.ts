/**
 * Parity tests vs `apps/dashboard/lib/accounting-views.ts` (continuity chain,
 * seam helpers) and `apps/dashboard/lib/performance-ssot.ts` (day-return
 * guards) for CONTRACT.md §6.6: per-row day returns, ≤4-day forward-fill,
 * seam basis flat.
 */
import { describe, it, expect } from 'vitest';
import {
  buildNavSeries,
  calendarDaysBetween,
  chainNavContinuity,
  crossesNavSeam,
  derivedDayReturnPct,
  forwardFillCalendarGaps,
  isNavSeriesSeam,
  navContinuityStepPct,
  navRowContractLabel,
  MAX_DAY_RETURN_GAP_DAYS,
  type NavInputRow,
} from './nav-series';

const row = (partial: Partial<NavInputRow> & { date: string; nav: number }): NavInputRow => ({
  dayReturnPct: null,
  source: 'finalized_accounting',
  contract: 'finalized_accounting',
  seriesSeam: null,
  ...partial,
});

describe('contract labels', () => {
  it('labels unlabeled rows as legacy estimates, never finalized', () => {
    expect(navRowContractLabel({})).toBe('legacy_estimate');
    expect(navRowContractLabel({ source: 'finalized_accounting' })).toBe(
      'finalized_accounting',
    );
    expect(navRowContractLabel({ contract: 'legacy_estimate' })).toBe('legacy_estimate');
  });

  it('detects seams via the explicit flag or a source flip', () => {
    expect(isNavSeriesSeam({ seriesSeam: true }, 'legacy_nav_history')).toBe(true);
    expect(
      isNavSeriesSeam(
        { source: 'finalized_accounting' },
        'legacy_nav_history',
      ),
    ).toBe(true);
    expect(
      isNavSeriesSeam(
        { source: 'finalized_accounting' },
        'finalized_accounting',
      ),
    ).toBe(false);
    expect(crossesNavSeam({ source: 'finalized_accounting' }, null)).toBe(false);
  });
});

describe('derivedDayReturnPct (seam + gap guards)', () => {
  it('prefers the stored day return inside a run', () => {
    const tip = row({ date: '2026-09-24', nav: 100, dayReturnPct: 0.5 });
    const prior = row({ date: '2026-09-23', nav: 99 });
    expect(derivedDayReturnPct(tip, prior)).toBe(0.5);
  });

  it('refuses stored AND derived returns across a seam (#3767)', () => {
    const tip = row({
      date: '2026-09-09',
      nav: 110,
      dayReturnPct: 10,
      source: 'finalized_accounting',
      seriesSeam: true,
    });
    const prior = row({ date: '2026-09-08', nav: 100, source: 'legacy_nav_history' });
    expect(derivedDayReturnPct(tip, prior)).toBeNull();
  });

  it('derives from levels across short gaps (weekend + holiday)', () => {
    const tip = row({ date: '2026-09-24', nav: 102 });
    const prior = row({ date: '2026-09-20', nav: 100 });
    expect(derivedDayReturnPct(tip, prior)).toBeCloseTo(2, 6);
  });

  it('returns null across gaps wider than 4 days (finalizer holes)', () => {
    expect(MAX_DAY_RETURN_GAP_DAYS).toBe(4);
    const tip = row({ date: '2026-09-24', nav: 102 });
    const prior = row({ date: '2026-09-18', nav: 100 });
    expect(derivedDayReturnPct(tip, prior)).toBeNull();
  });

  it('returns null without a prior row', () => {
    expect(derivedDayReturnPct(row({ date: '2026-09-24', nav: 100 }), null)).toBeNull();
  });
});

describe('chainNavContinuity (seam-flat base-100)', () => {
  it('carries a seam basis change flat instead of drawing the jump', () => {
    const rows = [
      row({ date: '2026-09-08', nav: 100, source: 'legacy_nav_history' }),
      // +10% level jump from the source flip with no own day return.
      row({
        date: '2026-09-09',
        nav: 110,
        source: 'finalized_accounting',
        seriesSeam: true,
      }),
      row({ date: '2026-09-10', nav: 111.1, source: 'finalized_accounting' }),
    ];
    const chained = chainNavContinuity(rows);
    expect(chained[0].index).toBeCloseTo(100, 6);
    expect(chained[1].index).toBeCloseTo(100, 6); // flat across the seam
    expect(chained[2].index).toBeCloseTo(101, 6); // +1% on own run
  });

  it('caps implausible steps at flat (#4014)', () => {
    expect(
      navContinuityStepPct(
        row({ date: '2026-09-24', nav: 200 }),
        row({ date: '2026-09-23', nav: 100 }),
      ),
    ).toBe(0);
  });

  it('returns empty for empty input', () => {
    expect(chainNavContinuity([])).toEqual([]);
  });
});

describe('buildNavSeries (§6.6 points)', () => {
  it('emits per-row day returns with preserved contract labels', () => {
    const points = buildNavSeries([
      row({ date: '2026-09-22', nav: 99, dayReturnPct: 0.2 }),
      row({ date: '2026-09-23', nav: 99.5, dayReturnPct: 0.5 }),
      row({
        date: '2026-09-24',
        nav: 99.909,
        source: 'legacy_nav_history',
        contract: 'legacy_estimate',
      }),
    ]);
    expect(points).toHaveLength(3);
    // A stored day return is honored even on the first row (client parity:
    // `derivedDayReturnPct` prefers the row's own value; only derivation
    // needs a prior row).
    expect(points[0].dayReturnPct).toBe(0.2);
    expect(points[1].dayReturnPct).toBe(0.5);
    expect(points[2].contract).toBe('legacy_estimate');
    expect(points[0].index).toBeCloseTo(100, 6);
  });
});

describe('forwardFillCalendarGaps (≤4-day, flat)', () => {
  const points = () =>
    buildNavSeries([
      row({ date: '2026-09-20', nav: 100, dayReturnPct: 0.1 }),
      row({ date: '2026-09-23', nav: 101 }),
    ]);

  it('fills short gaps flat with null day returns', () => {
    const filled = forwardFillCalendarGaps(points());
    expect(filled.map((p) => p.date)).toEqual([
      '2026-09-20',
      '2026-09-21',
      '2026-09-22',
      '2026-09-23',
    ]);
    for (const p of filled.slice(1, 3)) {
      expect(p.dayReturnPct).toBeNull();
      expect(p.index).toBeCloseTo(filled[0].index, 9);
    }
  });

  it('leaves wider gaps broken (no invented sessions)', () => {
    const wide = buildNavSeries([
      row({ date: '2026-09-10', nav: 100, dayReturnPct: 0.1 }),
      row({ date: '2026-09-20', nav: 101 }),
    ]);
    expect(forwardFillCalendarGaps(wide).map((p) => p.date)).toEqual([
      '2026-09-10',
      '2026-09-20',
    ]);
  });

  it('treats the exact 4-day gap as fillable, 5-day as a break', () => {
    const at4 = buildNavSeries([
      row({ date: '2026-09-20', nav: 100, dayReturnPct: 0.1 }),
      row({ date: '2026-09-24', nav: 101 }),
    ]);
    expect(forwardFillCalendarGaps(at4)).toHaveLength(5);
  });
});

describe('calendarDaysBetween', () => {
  it('counts signed UTC calendar days and rejects junk', () => {
    expect(calendarDaysBetween('2026-09-23', '2026-09-24')).toBe(1);
    expect(calendarDaysBetween('2026-09-24', '2026-09-23')).toBe(-1);
    expect(calendarDaysBetween('nope', '2026-09-24')).toBeNull();
  });
});
