const URL_PARSE_BASE = 'https://olympus.local';

/**
 * Portfolio ("the book") in-shell tabs after the redesign: Holdings · Theses.
 * Performance is now a dedicated route (/portfolio/performance).
 * Legacy values (allocations/activity/analysis/history/…) are remapped via
 * {@link mapPortfolioTabFromUrl} and canonicalized by
 * {@link canonicalizeLegacyPortfolioSearch} so old links keep working.
 */
export type PortfolioTabId = 'holdings' | 'theses';

export const VALID_PORTFOLIO_TABS: readonly PortfolioTabId[] = ['holdings', 'theses'];

/**
 * Legacy `?tab=` values that should be rewritten to a canonical tab.
 * - allocations/summary/positions/activity → holdings
 * - history/pm_process/analysis/pm_analysis/strategy → theses (PM intelligence
 *   now lives in Why; these legacy aliases land on Theses as a harmless fallback)
 * - thesis → thesis detail route
 */
export const LEGACY_PORTFOLIO_TAB_ALIASES = new Set([
  'summary',
  'allocations',
  'positions',
  'activity',
  'history',
  'pm_process',
  'analysis',
  'pm_analysis',
  'strategy',
  'thesis',
]);

export type PortfolioCanonicalTarget =
  | { kind: 'path'; href: string }
  | { kind: 'query'; href: string };

export function mapPortfolioTabFromUrl(raw: string | null): PortfolioTabId {
  if (!raw) return 'holdings';
  const r = raw.toLowerCase();
  if (
    r === 'theses' ||
    r === 'thesis' ||
    r === 'analysis' ||
    r === 'history' ||
    r === 'pm_process' ||
    r === 'pm_analysis' ||
    r === 'strategy'
  ) {
    return 'theses';
  }
  // allocations / summary / positions / activity / performance / unknown → holdings
  return VALID_PORTFOLIO_TABS.includes(r as PortfolioTabId) ? (r as PortfolioTabId) : 'holdings';
}

export function hrefWithQuery(pathname: string, params: URLSearchParams): string {
  const q = params.toString();
  return q ? `${pathname}?${q}` : pathname;
}

export function portfolioThesesPath(_pathname: string): string {
  // Path targets are consumed by Next's router, which applies basePath itself.
  return '/portfolio/theses';
}

export function replaceBrowserUrl(href: string): void {
  if (typeof window === 'undefined') return;
  window.history.replaceState(window.history.state, '', href);
}

export function currentSearchParams(fallback: { toString(): string }): URLSearchParams {
  if (typeof window !== 'undefined') return new URLSearchParams(window.location.search);
  return new URLSearchParams(fallback.toString());
}

export function currentPathname(fallback: string): string {
  if (typeof window !== 'undefined') return window.location.pathname;
  return fallback;
}

export function searchParamsFromHref(href: string): URLSearchParams {
  return new URL(href, URL_PARSE_BASE).searchParams;
}

export function canonicalizeLegacyPortfolioSearch(
  pathname: string,
  params: URLSearchParams,
  opts: { defaultHistoryDate?: string | null; lastUpdated?: string | null; docDate?: string | null } = {}
): PortfolioCanonicalTarget | null {
  const raw = params.get('tab');

  // Next's router applies the configured base path, so path targets stay app-relative.
  if (raw === 'performance') {
    return { kind: 'path', href: '/portfolio/performance' };
  }

  if (!raw || VALID_PORTFOLIO_TABS.includes(raw as PortfolioTabId) || !LEGACY_PORTFOLIO_TAB_ALIASES.has(raw)) {
    return null;
  }

  const p = new URLSearchParams(params.toString());
  const thesesPath = portfolioThesesPath(pathname);

  // → Holdings (the default book view): drop the tab + ancillary params.
  if (raw === 'summary' || raw === 'positions' || raw === 'allocations' || raw === 'activity') {
    p.delete('tab');
    p.delete('docKey');
    p.delete('date');
    p.delete('thesis');
    return { kind: 'query', href: hrefWithQuery(pathname, p) };
  }

  // Legacy thesis deep link → the thesis detail route (still a path).
  if (raw === 'thesis') {
    const thesis = p.get('thesis');
    p.delete('tab');
    p.delete('date');
    p.delete('docKey');
    p.delete('thesis');
    if (thesis) return { kind: 'path', href: `${thesesPath}/${encodeURIComponent(thesis)}` };
    p.set('tab', 'theses');
    return { kind: 'query', href: hrefWithQuery(pathname, p) };
  }

  // PM history / process docs → Theses tab, preserving/seeding the date.
  if (raw === 'history' || raw === 'pm_process') {
    p.set('tab', 'theses');
    if (!p.get('date')) p.set('date', opts.docDate ?? opts.lastUpdated ?? opts.defaultHistoryDate ?? '');
    if (!p.get('date')) p.delete('date');
    return { kind: 'query', href: hrefWithQuery(pathname, p) };
  }

  // analysis / pm_analysis / strategy → Theses tab.
  p.set('tab', 'theses');
  p.delete('docKey');
  p.delete('thesis');
  return { kind: 'query', href: hrefWithQuery(pathname, p) };
}

export function canonicalizeLegacyThesesSearch(
  params: URLSearchParams,
  pathname = '/portfolio/theses'
): PortfolioCanonicalTarget | null {
  const raw = params.get('tab');
  if (raw !== 'thesis' && raw !== 'theses') return null;

  const p = new URLSearchParams(params.toString());
  const thesis = raw === 'thesis' ? p.get('thesis') : null;
  p.delete('tab');
  p.delete('thesis');
  const thesesPath = portfolioThesesPath(pathname);

  if (thesis) return { kind: 'path', href: `${thesesPath}/${encodeURIComponent(thesis)}` };
  return { kind: 'query', href: hrefWithQuery(thesesPath, p) };
}
