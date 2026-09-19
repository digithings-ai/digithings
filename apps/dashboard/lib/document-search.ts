import type { Doc } from '@/lib/types';
import { buildPipelineHref, stageForDocumentKey, type PipelineStage } from '@/lib/pipeline-links';

export interface DocumentSearchItem {
  id: string;
  title: string;
  hint: string;
  href: string;
}

const STAGE_LABEL: Record<PipelineStage, string> = {
  inputs: 'Inputs',
  research: 'Research',
  synthesis: 'Synthesis',
  selection: 'Selection',
  decision: 'Decision',
  learning: 'Learning',
};

/** Human-ish display name for a doc when its title is thin (falls back to the document_key). */
function displayTitle(d: Doc): string {
  const t = (d.title || '').trim();
  if (t) return t;
  return d.path || d.segment || 'Document';
}

/** Rank: document_key-prefix (0) < title-prefix (1) < any substring match (2). Lower is better. */
function rank(d: Doc, q: string): number | null {
  const path = (d.path || '').toLowerCase();
  const title = (d.title || '').toLowerCase();
  const segment = (d.segment || '').toLowerCase();
  const type = (d.type || '').toLowerCase();
  if (path.startsWith(q)) return 0;
  if (title.startsWith(q)) return 1;
  if (path.includes(q) || title.includes(q) || segment.includes(q) || type.includes(q)) return 2;
  return null;
}

/**
 * Cross-day document discovery for the command palette. Matches a ticker/segment/title query
 * against `docs` and deep-links each hit to its Pipeline node (locked grammar, F2).
 * Returns `[]` for a blank query — search is keyed, never a full dump.
 */
export function buildDocumentSearchItems(docs: Doc[], query: string, limit = 8): DocumentSearchItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];

  const scored: { doc: Doc; r: number }[] = [];
  for (const d of docs) {
    if (!d.path) continue;
    const r = rank(d, q);
    if (r === null) continue;
    scored.push({ doc: d, r });
  }

  scored.sort((a, b) => {
    if (a.r !== b.r) return a.r - b.r;
    // Stable secondary sort: most recent date first, then title.
    const dateCmp = (b.doc.date || '').localeCompare(a.doc.date || '');
    if (dateCmp !== 0) return dateCmp;
    return displayTitle(a.doc).localeCompare(displayTitle(b.doc));
  });

  return scored.slice(0, limit).map(({ doc: d }) => {
    const stage = stageForDocumentKey(d.path);
    const stageLabel = stage ? STAGE_LABEL[stage] : 'Document';
    return {
      id: `doc-${d.id}`,
      title: displayTitle(d),
      hint: `${d.date} · ${stageLabel}`,
      href: buildPipelineHref({ date: d.date, stage, node: d.path }),
    };
  });
}
