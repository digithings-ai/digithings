import type { Doc } from './types';
import { MANIFEST_BY_KEY } from './research-manifest';

export const RESEARCH_CATEGORY_ORDER = [
  'Digest',
  'Market Analysis',
  'Sectors',
  'Intelligence',
  'Research Papers',
  'Deep Dives',
  'Weekly / Monthly',
  'Positions',
  'Portfolio',
  'Evolution',
  'Other',
] as const;

/**
 * Returns the permanent display name for a document.
 *
 * Priority:
 * 1. `d.title` from the DB — the canonical name written at publish time.
 * 2. Manifest entry name — fallback for rows published before canonical titles
 *    were enforced (e.g. very old baseline rows with no title).
 * 3. Cleaned path — last resort.
 */
export function canonicalResearchTitle(d: Doc): string {
  // DB title is the source of truth when present
  const rawTitle = (d.title || '').trim();
  if (rawTitle) {
    // Light cleanup: strip any legacy date / "Delta" / "Analysis" suffixes
    // that pre-canonical rows may have stored (one-time transitional guard).
    return rawTitle
      .replace(/\s*—\s*\d{4}-\d{2}-\d{2}.*$/, '')
      .replace(/\s*\(Delta\)\s*$/, '')
      .replace(/\s+Analysis\s*$/i, '')
      .trim() || rawTitle;
  }

  // Fallback: manifest canonical name for docs without a DB title
  const docKey = (d.path || '').toLowerCase();
  const manifest = MANIFEST_BY_KEY.get(docKey);
  if (manifest) return manifest.name;

  // Last resort: clean the path stem
  const raw = d.filename || d.path || '';
  return raw
    .replace(/\s*—\s*\d{4}-\d{2}-\d{2}$/, '')
    .replace(/^Sector Delta\s*—\s*/i, '')
    .replace(/\.delta\.md$/i, '')
    .replace(/-/g, ' ')
    .trim() || raw;
}

export function categorizeResearchDoc(d: Doc): string {
  const key = (d.path || d.filename || '').toLowerCase();
  const seg = (d.segment || '').toLowerCase();
  const type = (d.type || '').toLowerCase();

  if (key === 'digest') return 'Digest';

  // Manifest-registered docs get their canonical category
  const manifest = MANIFEST_BY_KEY.get(key);
  if (manifest) return manifest.category;

  if (key.startsWith('research/papers/')) return 'Research Papers';
  if (key.startsWith('research/deep-dives/') || key.startsWith('research/themes/') || key.startsWith('deep-dives/'))
    return 'Deep Dives';
  if (key.startsWith('research/')) return 'Deep Dives';
  if (key.startsWith('weekly/') || key.startsWith('monthly/')) return 'Weekly / Monthly';
  if (key.startsWith('evolution/')) return 'Evolution';
  if (seg.includes('rebalance') || seg.includes('deliberation') || seg.includes('portfolio') || seg.includes('opportunity'))
    return 'Portfolio';
  if (key.startsWith('positions/') || seg.includes('position')) return 'Positions';
  if (type.includes('weekly') || type.includes('monthly')) return 'Weekly / Monthly';
  if (type.includes('deep dive')) return 'Deep Dives';

  // Path-based category for delta docs (legacy / non-manifest)
  if (key.startsWith('deltas/sectors/')) return 'Sectors';
  if (key.startsWith('deltas/alt/')) return 'Intelligence';
  if (key.startsWith('deltas/')) return 'Market Analysis';

  if (
    seg.includes('macro') ||
    seg.includes('bonds') ||
    seg.includes('commodities') ||
    seg.includes('forex') ||
    seg.includes('crypto') ||
    seg.includes('international') ||
    seg.includes('equities') ||
    seg.includes('us-equities')
  )
    return 'Market Analysis';
  if (d.category?.toLowerCase() === 'sector' || seg.includes('sector')) return 'Sectors';
  if (seg.includes('alt') || seg.includes('institutional')) return 'Intelligence';
  return 'Other';
}

/** Long-form / reference research surfaced on the Knowledge base tab (not the daily run list). */
export function isKnowledgeBaseDoc(d: Doc): boolean {
  const cat = categorizeResearchDoc(d);
  return cat === 'Deep Dives' || cat === 'Weekly / Monthly' || cat === 'Research Papers';
}

/** Per-day run artifacts, digest, and dated research outputs (excludes knowledge-base reference docs). */
export function isDailyResearchDoc(d: Doc): boolean {
  return !isKnowledgeBaseDoc(d);
}
