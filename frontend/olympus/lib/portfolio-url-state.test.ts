import { describe, expect, it } from 'vitest';
import {
  VALID_PORTFOLIO_TABS,
  canonicalizeLegacyPortfolioSearch,
  canonicalizeLegacyThesesSearch,
  ledgerHref,
  mapPortfolioTabFromUrl,
  searchParamsFromHref,
  thesisDetailHref,
  tickerDossierHref,
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

  it('canonicalizes legacy thesis deep links to the query-param thesis route (#1760)', () => {
    const target = canonicalizeLegacyPortfolioSearch(
      '/olympus/portfolio',
      new URLSearchParams('tab=thesis&thesis=SHY&date=2026-06-17')
    );

    // `kind: 'path'` selects router.replace (which applies basePath) — the
    // detail view sits on another pathname, so it needs a real navigation.
    expect(target).toEqual({ kind: 'path', href: '/portfolio/theses?thesis=SHY' });
  });

  it('builds every thesis detail href as a query on the static theses route (#1760)', () => {
    // A dynamic `[thesisId]` segment under `output: 'export'` 404s on any id the
    // build did not enumerate; the query form serves ids created after a deploy.
    expect(thesisDetailHref('tariff-oil-stagflation-risk')).toBe(
      '/portfolio/theses?thesis=tariff-oil-stagflation-risk'
    );
    expect(thesisDetailHref('_unlinked')).toBe('/portfolio/theses?thesis=_unlinked');
  });

  it('encodes ids that would otherwise break the query string', () => {
    expect(thesisDetailHref('a&b=c')).toBe('/portfolio/theses?thesis=a%26b%3Dc');
    expect(searchParamsFromHref(thesisDetailHref('a&b=c')).get('thesis')).toBe('a&b=c');
    expect(searchParamsFromHref(thesisDetailHref('semis / AI')).get('thesis')).toBe('semis / AI');
  });

  it('canonicalizes legacy theses tab once on the theses page', () => {
    const target = canonicalizeLegacyThesesSearch(new URLSearchParams('tab=theses&date=2026-06-17'));

    expect(target).toEqual({ kind: 'query', href: '/portfolio/theses?date=2026-06-17' });
  });

  it('canonicalizes a ?tab=thesis deep link on the theses page to the query form (#1760)', () => {
    const target = canonicalizeLegacyThesesSearch(new URLSearchParams('tab=thesis&thesis=MT1'));

    expect(target).toEqual({ kind: 'path', href: '/portfolio/theses?thesis=MT1' });
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

  it('builds ticker dossier and ledger hrefs', () => {
    expect(tickerDossierHref('gld')).toBe('/portfolio/tickers?ticker=GLD');
    expect(ledgerHref()).toBe('/portfolio/ledger');
    expect(ledgerHref({ date: '2026-08-20', ticker: 'gld' })).toBe(
      '/portfolio/ledger?date=2026-08-20&ticker=GLD'
    );
  });
});
