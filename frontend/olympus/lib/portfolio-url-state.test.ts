import { describe, expect, it } from 'vitest';
import {
  VALID_PORTFOLIO_TABS,
  canonicalizeLegacyPortfolioSearch,
  canonicalizeLegacyThesesSearch,
  mapPortfolioTabFromUrl,
} from './portfolio-url-state';

describe('portfolio-url-state', () => {
  it('exposes the two canonical in-shell tabs (performance is now a dedicated route)', () => {
    expect([...VALID_PORTFOLIO_TABS]).toEqual(['holdings', 'theses']);
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
    // performance is no longer an in-shell tab; it should map to holdings as unknown
    expect(mapPortfolioTabFromUrl('performance')).toBe('holdings');
  });

  it('canonicalizes ?tab=performance to /portfolio/performance (dedicated route)', () => {
    const target = canonicalizeLegacyPortfolioSearch(
      '/olympus/portfolio',
      new URLSearchParams('tab=performance')
    );

    expect(target).toEqual({ kind: 'path', href: '/portfolio/performance' });
  });

  it('keeps the Performance target app-relative when no deployment base is present', () => {
    const target = canonicalizeLegacyPortfolioSearch(
      '/portfolio',
      new URLSearchParams('tab=performance&extra=foo')
    );

    expect(target).toEqual({ kind: 'path', href: '/portfolio/performance' });
  });

  it('canonicalizes legacy thesis deep links to the thesis route', () => {
    const target = canonicalizeLegacyPortfolioSearch(
      '/olympus/portfolio',
      new URLSearchParams('tab=thesis&thesis=SHY&date=2026-06-17')
    );

    expect(target).toEqual({ kind: 'path', href: '/portfolio/theses/SHY' });
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
