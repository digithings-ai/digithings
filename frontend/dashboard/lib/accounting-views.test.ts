import { describe, expect, it } from 'vitest';
import {
  AccountingNavContractError,
  accountingNavToHistoryShape,
  assertAccountingNavQueryOk,
  contributionsSumToDayReturn,
  isMissingPublicRelationError,
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

  it('labels a mixed calendar series from the tip row, never any historical finalized row', () => {
    expect(
      navSeriesContractLabel([
        { date: '2026-08-01', source: 'finalized_accounting', contract: 'finalized_accounting' },
        { date: '2026-09-04', source: 'legacy_nav_history', contract: 'legacy_estimate' },
      ])
    ).toBe('legacy_estimate');
    expect(
      navSeriesContractLabel([
        { date: '2026-09-04', source: 'legacy_nav_history', contract: 'legacy_estimate' },
        { date: '2026-08-01', source: 'finalized_accounting', contract: 'finalized_accounting' },
      ])
    ).toBe('legacy_estimate');
    expect(
      navSeriesContractLabel([
        { date: '2026-08-01', source: 'legacy_nav_history', contract: 'legacy_estimate' },
        { date: '2026-09-04', source: 'finalized_accounting', contract: 'finalized_accounting' },
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

describe('accounting NAV fail-closed contract (#3029)', () => {
  it('detects PostgREST missing-relation errors', () => {
    expect(
      isMissingPublicRelationError({
        code: 'PGRST205',
        message: "Could not find the table 'public.public_accounting_nav_history' in the schema cache",
      })
    ).toBe(true);
    expect(isMissingPublicRelationError({ code: '42501', message: 'permission denied' })).toBe(
      false
    );
  });

  it('throws AccountingNavContractError naming the view and migrations on PGRST205', () => {
    expect(() =>
      assertAccountingNavQueryOk({
        code: 'PGRST205',
        message: "Could not find the table 'public.public_accounting_nav_history' in the schema cache",
      })
    ).toThrow(AccountingNavContractError);
    try {
      assertAccountingNavQueryOk({ code: 'PGRST205', message: 'schema cache' });
    } catch (err) {
      expect(err).toBeInstanceOf(AccountingNavContractError);
      const e = err as AccountingNavContractError;
      expect(e.view).toBe('public_accounting_nav_history');
      expect(e.message).toContain('072–074');
      expect(e.message).toContain('public_accounting_nav_history');
    }
  });

  it('does not throw when the query succeeded', () => {
    expect(() => assertAccountingNavQueryOk(null)).not.toThrow();
    expect(() => assertAccountingNavQueryOk(undefined)).not.toThrow();
  });
});
