export type PortfolioTabId = 'allocations' | 'performance' | 'analysis' | 'activity';

export const VALID_PORTFOLIO_TABS: readonly PortfolioTabId[] = [
  'allocations',
  'performance',
  'analysis',
  'activity',
];

export const LEGACY_PORTFOLIO_TAB_ALIASES = new Set([
  'summary',
  'history',
  'pm_process',
  'thesis',
  'positions',
  'theses',
  'pm_analysis',
]);

export type PortfolioCanonicalTarget =
  | { kind: 'path'; href: string }
  | { kind: 'query'; href: string };

export function mapPortfolioTabFromUrl(raw: string | null): PortfolioTabId {
  if (!raw || raw === 'summary') return 'allocations';
  if (raw === 'history' || raw === 'pm_process') return 'analysis';
  if (raw === 'thesis' || raw === 'theses' || raw === 'pm_analysis' || raw === 'positions') {
    return 'allocations';
  }
  if (VALID_PORTFOLIO_TABS.includes(raw as PortfolioTabId)) return raw as PortfolioTabId;
  return 'allocations';
}

export function hrefWithQuery(pathname: string, params: URLSearchParams): string {
  const q = params.toString();
  return q ? `${pathname}?${q}` : pathname;
}

export function portfolioThesesPath(pathname: string): string {
  const clean = pathname.replace(/\/+$/, '');
  if (clean.endsWith('/portfolio/theses')) return clean;
  if (clean.endsWith('/portfolio')) return `${clean}/theses`;
  return '/portfolio/theses';
}

export function replaceBrowserUrl(href: string): void {
  if (typeof window === 'undefined') return;
  window.history.replaceState(window.history.state, '', href);
}

export function canonicalizeLegacyPortfolioSearch(
  pathname: string,
  params: URLSearchParams,
  opts: { defaultHistoryDate?: string | null; lastUpdated?: string | null; docDate?: string | null } = {}
): PortfolioCanonicalTarget | null {
  const raw = params.get('tab');
  if (!raw || VALID_PORTFOLIO_TABS.includes(raw as PortfolioTabId) || !LEGACY_PORTFOLIO_TAB_ALIASES.has(raw)) {
    return null;
  }

  const p = new URLSearchParams(params.toString());
  const thesesPath = portfolioThesesPath(pathname);
  if (raw === 'summary' || raw === 'positions') {
    p.delete('tab');
    p.delete('docKey');
    p.delete('date');
    p.delete('thesis');
    return { kind: 'query', href: hrefWithQuery(pathname, p) };
  }

  if (raw === 'history') {
    p.set('tab', 'analysis');
    if (!p.get('date') && opts.defaultHistoryDate) p.set('date', opts.defaultHistoryDate);
    return { kind: 'query', href: hrefWithQuery(pathname, p) };
  }

  if (raw === 'pm_process') {
    p.set('tab', 'analysis');
    if (!p.get('date')) p.set('date', opts.docDate ?? opts.lastUpdated ?? opts.defaultHistoryDate ?? '');
    if (!p.get('date')) p.delete('date');
    return { kind: 'query', href: hrefWithQuery(pathname, p) };
  }

  if (raw === 'thesis') {
    const thesis = p.get('thesis');
    p.delete('tab');
    p.delete('date');
    p.delete('docKey');
    p.delete('thesis');
    if (thesis) return { kind: 'path', href: `${thesesPath}/${encodeURIComponent(thesis)}` };
    return { kind: 'path', href: thesesPath };
  }

  if (raw === 'theses' || raw === 'pm_analysis') {
    p.delete('tab');
    p.delete('docKey');
    p.delete('date');
    p.delete('thesis');
    return { kind: 'path', href: hrefWithQuery(thesesPath, p) };
  }

  return null;
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
