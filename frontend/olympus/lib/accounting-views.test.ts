import { describe, expect, it } from 'vitest';
import {
  accountingNavToHistoryShape,
  contributionsSumToDayReturn,
  navSeriesContractLabel,
} from './accounting-views';

describe('accounting-views helpers (#2599)', () => {
  it('maps curated NAV rows without dropping the source label', () => {
    const mapped = accountingNavToHistoryShape({
      date: '2026-08-01',
      nav: 101.5,
      cash_pct: 20,
      invested_pct: 80,
      day_return_pct: 1.5,
      source: 'finalized_accounting',
      contract: 'finalized_accounting',
    });
    expect(mapped.source).toBe('finalized_accounting');
    expect(mapped.nav).toBe(101.5);
  });

  it('labels a mixed calendar series by presence of finalized rows (not blended values)', () => {
    expect(
      navSeriesContractLabel([
        { source: 'legacy_nav_history', contract: 'legacy_estimate' },
        { source: 'finalized_accounting', contract: 'finalized_accounting' },
      ])
    ).toBe('finalized_accounting');
    expect(
      navSeriesContractLabel([{ source: 'legacy_nav_history', contract: 'legacy_estimate' }])
    ).toBe('legacy_estimate');
    expect(navSeriesContractLabel([])).toBe('empty');
  });

  it('requires daily contributions to sum to the shown NAV day return', () => {
    expect(contributionsSumToDayReturn([0.8, 0.5, 0.2], 1.5)).toBe(true);
    expect(contributionsSumToDayReturn([0.8, 0.5], 1.5)).toBe(false);
  });
});
