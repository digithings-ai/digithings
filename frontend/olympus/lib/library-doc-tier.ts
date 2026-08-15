import type { Doc, ResearchChangelogMeta } from './types';

/** Library filter tabs: default Research hides portfolio machine artifacts and evolution. */
export type LibraryScope = 'research' | 'portfolio' | 'evolution' | 'all';

export type DocLibraryTier = 'research' | 'portfolio' | 'evolution';

const PORTFOLIO_KEYS = new Set(
  [
    'rebalance-decision.json',
    'deliberation.md',
    'deliberation.json',
    'deliberation-transcript.json',
    'opportunity-screener.json',
  ].map((k) => k.toLowerCase())
);

/** Legacy artifact; excluded from PM artifact lists. */
export function isPortfolioRecommendationPath(path: string): boolean {
  return (path || '').toLowerCase().includes('portfolio-recommendation');
}

function pathKey(path: string): string {
  return (path || '').toLowerCase().split('/').pop() || '';
}

/** Primary tier for routing docs into Research vs Portfolio vs Evolution lists. */
export function getDocLibraryTier(d: Pick<Doc, 'path' | 'segment' | 'type'>): DocLibraryTier {
  const p = (d.path || '').toLowerCase();
  if (p.startsWith('evolution/')) return 'evolution';
  // Track B (PM) artifacts — thesis exploration, vehicle mapping, screener, deliberation, recs all belong here
  if (
    p.startsWith('market-thesis-exploration/') ||
    p.startsWith('thesis-vehicle-map/') ||
    p.startsWith('opportunity-screen/') ||
    p.startsWith('pm-allocation-memo/') ||
    p.startsWith('deliberation-transcript-index/') ||
    p.startsWith('deliberation-transcript/') ||
    p.startsWith('asset-recommendations/')
  ) {
    return 'portfolio';
  }
  const file = pathKey(p);
  if (PORTFOLIO_KEYS.has(file)) return 'portfolio';
  const seg = (d.segment || '').toLowerCase();
  if (
    seg.includes('deliberation') ||
    seg.includes('rebalance') ||
    seg.includes('portfolio') ||
    seg.includes('opportunity')
  ) {
    return 'portfolio';
  }
  const typ = (d.type || '').toLowerCase();
  if (typ.includes('rebalance') || typ.includes('deliberation')) return 'portfolio';
  return 'research';
}

export function docMatchesLibraryScope(
  d: Pick<Doc, 'path' | 'segment' | 'type'>,
  scope: LibraryScope
): boolean {
  if (scope === 'all') return true;
  const tier = getDocLibraryTier(d);
  const file = pathKey(d.path);

  if (scope === 'research') {
    if (tier !== 'research') return false;
    // Machine artifacts: hide from research (surfaced via structured views / Portfolio / delta panel)
    if (file === 'delta-request.json') return false;
    const full = (d.path || '').toLowerCase();
    if (full.startsWith('document-deltas/')) return false;
    // Per-segment deltas (deltas/* incl. deltas/sectors/* and deltas/alt/*) are research docs
    // and should NOT be hidden — they ARE the primary research content.
    return true;
  }
  if (scope === 'portfolio') {
    return tier === 'portfolio';
  }
  if (scope === 'evolution') {
    return tier === 'evolution';
  }
  return true;
}

/** True if evolution_sources payload has no meaningful content (draft outline). */
export function isEvolutionSourcesEmpty(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return true;
  const p = payload as Record<string, unknown>;
  if (String(p.doc_type || '') !== 'evolution_sources') return false;
  const body = p.body;
  if (!body || typeof body !== 'object' || Array.isArray(body)) return true;
  const b = body as Record<string, unknown>;
  const notes = String(b.notes || '').trim();
  const ratings = b.source_ratings;
  const hasRatings = Array.isArray(ratings) && ratings.some((r) => r && typeof r === 'object');
  return !notes && !hasRatings;
}

/** Whether a changed_paths entry likely relates to a document_key (for delta touched badge). */
export function docAffectedByDeltaPaths(docPath: string, changedPaths: string[]): boolean {
  if (!changedPaths.length) return false;
  const key = (docPath || '').toLowerCase();
  const file = pathKey(key);

  const digestPrefixes = (p: string) =>
    p.startsWith('/regime') ||
    p.startsWith('/market_data') ||
    p.startsWith('/actionable') ||
    p.startsWith('/risks') ||
    p.startsWith('/segments') ||
    p.startsWith('/portfolio') ||
    p.startsWith('/digest') ||
    p === '/';

  if (file === 'digest' || key === 'digest') {
    return changedPaths.some(digestPrefixes);
  }

  const stem = file.replace(/\.json$/i, '').replace(/\.md$/i, '');
  if (!stem || stem === 'delta-request') return false;

  return changedPaths.some((p) => {
    const low = p.toLowerCase();
    return low.includes(stem.replace(/-/g, '')) || low.includes(stem.replace(/-/g, '_')) || low.includes(`/${stem}`) || low.includes(`/${stem.replace(/-/g, '_')}`);
  });
}

/** Count distinct delta paths (changed_paths ∪ op_paths) that map to this library row. */
export function countDeltaTouchesForDoc(
  docPath: string,
  changedPaths: string[],
  opPaths: string[]
): number {
  const unique = [...new Set([...changedPaths, ...opPaths].filter(Boolean))];
  let n = 0;
  for (const p of unique) {
    if (docAffectedByDeltaPaths(docPath, [p])) n += 1;
  }
  return n;
}

function normPathKey(p: string): string {
  return (p || '').toLowerCase().trim();
}

/** Badge count from research_changelog items (per-document delta pipeline). */
export function countResearchChangelogTouchesForDoc(docPath: string, meta: ResearchChangelogMeta | null): number {
  if (!meta?.items?.length) return 0;
  const key = normPathKey(docPath);
  let n = 0;
  for (const it of meta.items) {
    const tk = normPathKey(it.target_document_key);
    if (!tk) continue;
    if (key === tk || key.endsWith(tk) || tk.endsWith(key)) n += 1;
  }
  return n;
}
