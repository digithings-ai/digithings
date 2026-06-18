import { describe, expect, it } from 'vitest';
import {
  canonicalizeLegacyPortfolioSearch,
  canonicalizeLegacyThesesSearch,
  mapPortfolioTabFromUrl,
} from './portfolio-url-state';

describe('portfolio-url-state', () => {
  it('maps legacy thesis tabs away from shell-owned tabs', () => {
    expect(mapPortfolioTabFromUrl('theses')).toBe('allocations');
    expect(mapPortfolioTabFromUrl('thesis')).toBe('allocations');
    expect(mapPortfolioTabFromUrl('activity')).toBe('activity');
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

  it('rewrites historical aliases without path navigation', () => {
    const target = canonicalizeLegacyPortfolioSearch('/portfolio', new URLSearchParams('tab=history'), {
      defaultHistoryDate: '2026-06-18',
    });

    expect(target).toEqual({ kind: 'query', href: '/portfolio?tab=analysis&date=2026-06-18' });
  });
});
