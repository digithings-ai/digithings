import type { Doc } from '@/lib/types';

/**
 * Faceted cross-day Documents archive — DEFERRED this cycle (2026-06-24 redesign).
 *
 * The standalone archive (MiniCalendar + per-date accordion + carry-forward manifest)
 * was retired because the live DB holds a single day; per-day reading lives in Pipeline
 * node-detail and cross-day discovery lives in the command palette
 * (`buildDocumentSearchItems`). A future faceted archive should gate its route/nav entry
 * on THIS predicate — until documents span more than one date it must not render at all
 * (empty-state discipline: absent, not narrating its emptiness).
 *
 * When this flips true, rebuild the archive over `research-doc-categorize.ts`
 * (`categorizeResearchDoc` / `RESEARCH_CATEGORY_ORDER`), which were retained for exactly this.
 */
export function shouldShowDocumentArchive(docs: Doc[]): boolean {
  const dates = new Set<string>();
  for (const d of docs) {
    if (d.date) dates.add(d.date);
  }
  return dates.size > 1;
}
