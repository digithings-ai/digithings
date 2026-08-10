import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * `/portfolio/theses` route behaviour (#1760) — one static page, two jobs:
 * `?thesis=<id>` renders that thesis' detail view, no param falls through to the
 * legacy hub redirect. Node environment (no jsdom), so effects are driven the
 * way `components/legacy-spa-redirect.test.tsx` does: stub `useEffect` to run
 * synchronously and capture `router.replace`.
 *
 * Must stay `.test.ts` — `vitest.config.ts` includes `app/**\/*.test.ts` only,
 * so an `app/**\/*.test.tsx` would silently never run.
 */
const replace = vi.fn();
let search = new URLSearchParams();

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  return { ...actual, useEffect: (fn: () => void) => fn() };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => search,
}));

vi.mock('@/components/AtlasLoader', () => ({ default: () => null }));
vi.mock('@/components/page-skeleton', () => ({ default: () => null }));

// The detail view reads the dashboard context and a pile of chart libraries;
// this suite only asserts the routing contract, so stub it and echo the id.
vi.mock('@/components/portfolio/theses/ThesisDetailPageInner', () => ({
  default: ({ thesisId }: { thesisId: string }) =>
    createElement('div', { 'data-thesis-id': thesisId }, `detail:${thesisId}`),
}));

import PortfolioThesesPage from './page';

beforeEach(() => {
  replace.mockClear();
  search = new URLSearchParams();
});

describe('/portfolio/theses (#1760 — query-param detail route)', () => {
  it('renders the detail view for `?thesis=<id>` instead of 404ing on a missing segment', () => {
    search = new URLSearchParams({ thesis: 'tariff-oil-stagflation-risk' });
    const html = renderToStaticMarkup(createElement(PortfolioThesesPage));
    expect(html).toContain('detail:tariff-oil-stagflation-risk');
    expect(replace).not.toHaveBeenCalled();
  });

  it('serves an id the build never saw — the whole point of the query route', () => {
    search = new URLSearchParams({ thesis: 'thesis-created-after-the-deploy' });
    const html = renderToStaticMarkup(createElement(PortfolioThesesPage));
    expect(html).toContain('detail:thesis-created-after-the-deploy');
  });

  it('keeps the `_unlinked` shelf reachable', () => {
    search = new URLSearchParams({ thesis: '_unlinked' });
    expect(renderToStaticMarkup(createElement(PortfolioThesesPage))).toContain('detail:_unlinked');
  });

  it('trims surrounding whitespace out of the id', () => {
    search = new URLSearchParams({ thesis: '  asia-semi-contagion  ' });
    const html = renderToStaticMarkup(createElement(PortfolioThesesPage));
    expect(html).toContain('detail:asia-semi-contagion');
  });

  it('falls through to the hub redirect with no `?thesis=`', () => {
    renderToStaticMarkup(createElement(PortfolioThesesPage));
    expect(replace).toHaveBeenCalledWith('/portfolio?tab=theses');
  });

  it('treats a blank `?thesis=` as the hub, not a missing thesis', () => {
    search = new URLSearchParams({ thesis: '   ' });
    renderToStaticMarkup(createElement(PortfolioThesesPage));
    expect(replace).toHaveBeenCalledWith('/portfolio?tab=theses');
  });

  it('preserves `?date=` through the hub redirect', () => {
    search = new URLSearchParams({ date: '2026-07-31' });
    renderToStaticMarkup(createElement(PortfolioThesesPage));
    expect(replace).toHaveBeenCalledWith('/portfolio?tab=theses&date=2026-07-31');
  });
});
