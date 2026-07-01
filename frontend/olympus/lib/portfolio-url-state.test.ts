import { describe, expect, it } from 'vitest';
import {
  VALID_PORTFOLIO_TABS,
  canonicalizeLegacyPortfolioSearch,
  canonicalizeLegacyThesesSearch,
  mapPortfolioTabFromUrl,
} from './portfolio-url-state';

describe('portfolio-url-state', () => {
  it('exposes the three canonical book tabs', () => {
    expect([...VALID_PORTFOLIO_TABS]).toEqual(['holdings', 'theses', 'performance']);
  });

  it('resolves every legacy alias to a canonical tab', () => {
    // → holdings
    expect(mapPortfolioTabFromUrl(null)).toBe('holdings');
    expect(mapPortfolioTabFromUrl('allocations')).toBe('holdings');
    expect(mapPortfolioTabFromUrl('summary')).toBe('holdings');
    expect(mapPortfolioTabFromUrl('positions')).toBe('holdings');
    expect(mapPortfolioTabFromUrl('activity')).toBe('holdings');
    // → theses (theses + PM intelligence/history)
    expect(mapPortfolioTabFromUrl('theses')).toBe('theses');
    expect(mapPortfolioTabFromUrl('thesis')).toBe('theses');
    expect(mapPortfolioTabFromUrl('analysis')).toBe('theses');
    expect(mapPortfolioTabFromUrl('history')).toBe('theses');
    // → performance
    expect(mapPortfolioTabFromUrl('performance')).toBe('performance');
  });

  it('canonicalizes legacy thesis deep links to the thesis route', () => {
    const target = canonicalizeLegacyPortfolioSearch(
      '/olympus/portfolio',
      new URLSearchParams('tab=thesis&thesis=SHY&date=2026-06-17')
    );

    expect(target).toEqual({ kind: 'path', href: '/olympus/portfolio/theses/SHY' });
  });

  it('canonicalizes legacy theses tab once on the theses page', () => {
    const target = canonicalizeLegacyThesesSearch(new URLSearchParams('tab=theses&date=2026-06-17'));

    expect(target).toEqual({ kind: 'query', href: '/portfolio/theses?date=2026-06-17' });
  });

  it('rewrites the historical alias to the Theses tab, seeding the date', () => {
    const target = canonicalizeLegacyPortfolioSearch('/portfolio', new URLSearchParams('tab=history'), {
      defaultHistoryDate: '2026-06-18',
    });

    expect(target).toEqual({ kind: 'query', href: '/portfolio?tab=theses&date=2026-06-18' });
  });

  it('drops the tab for legacy allocations/activity (→ holdings default)', () => {
    expect(canonicalizeLegacyPortfolioSearch('/portfolio', new URLSearchParams('tab=activity'))).toEqual({
      kind: 'query',
      href: '/portfolio',
    });
  });
});
