import type { Doc } from '@/lib/types';

// ─────────────────────────────────────────────────────────────────────────────
// PM document grouping
// ─────────────────────────────────────────────────────────────────────────────

export type PmDocGroup =
  | { kind: 'thesis'; docs: Doc[] }
  | { kind: 'recommendations'; docs: Doc[] }
  | { kind: 'deliberations'; docs: Doc[] }
  | { kind: 'memo'; docs: Doc[] };

/** Extract the ticker from a nested PM document_key (case-insensitive). */
export function extractTickerFromPmKey(path: string): string | null {
  const m = (path || '').match(
    /(?:deliberation-transcript|asset-recommendations)\/[^/]+\/([^/]+)\.json$/i
  );
  return m ? m[1].toUpperCase() : null;
}

/** Stable display title for a PM artifact row (date-independent). */
export function canonicalPmTitle(path: string): string {
  const p = (path || '').toLowerCase();
  if (p.startsWith('market-thesis-exploration/')) return 'Thesis Exploration';
  if (p.startsWith('thesis-vehicle-map/'))         return 'Thesis Vehicle Map';
  if (p.includes('opportunity-screen'))             return 'Opportunity Screener';
  if (p.startsWith('pm-allocation-memo/'))          return 'PM Allocation Memo';
  // Per-ticker docs: show just the ticker (section header provides context)
  if (p.startsWith('deliberation-transcript/') || p.startsWith('asset-recommendations/')) {
    const ticker = extractTickerFromPmKey(path);
    return ticker ?? path.split('/').pop()?.replace(/\.json$/i, '') ?? path;
  }
  return path.split('/').pop()?.replace(/\.json$/i, '') ?? path;
}

/**
 * Group PM artifact docs into the canonical Intelligence tab sections:
 *
 *   1. Thesis        — Thesis Exploration, Thesis Vehicle Map, Opportunity Screener
 *   2. Recommendations — one row per analyzed ticker (asset-recommendations/*)
 *   3. Deliberations — one row per analyzed ticker (deliberation-transcript/*)
 *   4. PM Memo       — PM Allocation Memo + fallback unknown docs
 *
 * Hidden: `deliberation-transcript-index/` (machine use only).
 */
export function groupPmDocs(docs: Doc[]): PmDocGroup[] {
  const thesisDocs: Doc[] = [];
  const recDocs: Doc[] = [];
  const delDocs: Doc[] = [];
  const memoDocs: Doc[] = [];

  for (const d of docs) {
    const p = (d.path || '').toLowerCase();

    if (p.startsWith('deliberation-transcript-index/')) continue;

    if (
      p.startsWith('market-thesis-exploration/') ||
      p.startsWith('thesis-vehicle-map/') ||
      p.includes('opportunity-screen')
    ) {
      thesisDocs.push(d);
      continue;
    }

    if (p.startsWith('asset-recommendations/')) {
      recDocs.push(d);
      continue;
    }

    if (p.startsWith('deliberation-transcript/')) {
      delDocs.push(d);
      continue;
    }

    memoDocs.push(d);
  }

  // Thesis: exploration → vehicle map → screener
  thesisDocs.sort((a, b) => {
    const order = (p: string) => {
      const low = p.toLowerCase();
      if (low.startsWith('market-thesis-exploration/')) return 0;
      if (low.startsWith('thesis-vehicle-map/')) return 1;
      return 2;
    };
    return order(a.path) - order(b.path);
  });

  // Recommendations + Deliberations: alphabetical by ticker
  const byTicker = (d: Doc) => extractTickerFromPmKey(d.path) ?? d.path;
  recDocs.sort((a, b) => byTicker(a).localeCompare(byTicker(b)));
  delDocs.sort((a, b) => byTicker(a).localeCompare(byTicker(b)));

  // Memo: pm-allocation-memo first
  memoDocs.sort((a, b) => {
    const rank = (p: string) => (p.toLowerCase().startsWith('pm-allocation-memo/') ? 0 : 1);
    return rank(a.path) - rank(b.path);
  });

  const groups: PmDocGroup[] = [];
  if (thesisDocs.length > 0) groups.push({ kind: 'thesis', docs: thesisDocs });
  if (recDocs.length > 0)    groups.push({ kind: 'recommendations', docs: recDocs });
  if (delDocs.length > 0)    groups.push({ kind: 'deliberations', docs: delDocs });
  if (memoDocs.length > 0)   groups.push({ kind: 'memo', docs: memoDocs });

  return groups;
}

export const ALLOCATION_PALETTE = [
  '#3B82F6',
  '#10B981',
  '#F59E0B',
  '#EF4444',
  '#8B5CF6',
  '#06B6D4',
  '#F97316',
  '#EC4899',
  '#6366F1',
  '#14B8A6',
];

/** Stable accent color for a category / grouping key (hex, for inline styles). */
export function allocationAccentFromKey(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i += 1) h = (Math.imul(31, h) + key.charCodeAt(i)) | 0;
  return ALLOCATION_PALETTE[Math.abs(h) % ALLOCATION_PALETTE.length];
}

const CATEGORY_LABELS: Record<string, string> = {
  commodity_gold: 'Commodity — Gold',
  commodity_oil: 'Commodity — Oil',
  commodity_silver: 'Commodity — Silver',
  equity_sector: 'Equity Sector',
  equity_broad: 'Broad Equity',
  fixed_income_cash: 'Cash',
  fixed_income_short: 'Short Duration',
  fixed_income_long: 'Long Duration',
  fixed_income_tips: 'TIPS',
  crypto: 'Crypto',
  international: 'International',
  cash: 'Cash',
  uncategorized: 'Uncategorized',
};

export function formatAllocationCategory(cat: string | null | undefined): string {
  if (!cat) return '—';
  return CATEGORY_LABELS[cat] || cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

export const PM_DOC_ORDER = [
  'deliberation.md',
  'deliberation.json',
  'deliberation-transcript.json',
  'rebalance-decision.json',
  'opportunity-screener.json',
] as const;

export function pmDocSortKey(path: string): number {
  const low = path.toLowerCase();
  if (low.startsWith('pm-allocation-memo/')) return 0;
  if (low.includes('deliberation-transcript-index/')) return 1;
  if (low.startsWith('deliberation-transcript/')) return 2;
  if (low.startsWith('asset-recommendations/')) return 3;
  if (low.startsWith('thesis-vehicle-map/')) return 4;
  if (low.startsWith('market-thesis-exploration/')) return 5;
  const file = low.split('/').pop() || low;
  const i = (PM_DOC_ORDER as readonly string[]).indexOf(file);
  return i === -1 ? 50 : 10 + i;
}

export function sortPmDocs(docs: Doc[]): Doc[] {
  return [...docs].sort((a, b) => {
    const ka = pmDocSortKey(a.path);
    const kb = pmDocSortKey(b.path);
    if (ka !== kb) return ka - kb;
    return a.path.localeCompare(b.path);
  });
}

export type PieSliceDatum = { name: string; value: number; tooltipExtra?: string };

const MAX_PIE_SLICES = 14;

/** Bucket small slices into "Other" for readable pie charts. */
export function bucketAllocationsForPie(items: { name: string; value: number }[]): PieSliceDatum[] {
  const pos = items.filter((x) => x.value > 0.0001).sort((a, b) => b.value - a.value);
  if (pos.length <= MAX_PIE_SLICES) return pos.map(({ name, value }) => ({ name, value }));
  const head = pos.slice(0, MAX_PIE_SLICES - 1);
  const tail = pos.slice(MAX_PIE_SLICES - 1);
  const other = tail.reduce((s, x) => s + x.value, 0);
  const tooltipExtra = tail.map((t) => `${t.name}: ${t.value.toFixed(1)}%`).join(' · ');
  return [...head.map(({ name, value }) => ({ name, value })), { name: 'Other', value: other, tooltipExtra }];
}
