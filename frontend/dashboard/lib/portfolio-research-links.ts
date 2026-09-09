import type { Doc } from '@/lib/types';

/** Links to Research daily tab for digest + thesis-oriented global docs on a run date. */
export function buildResearchStripLinks(effHistoryDate: string | null, docs: Doc[] | undefined): { label: string; docKey: string }[] {
  if (!effHistoryDate || !docs?.length) return [];
  const keysOnDate = new Set<string>();
  for (const d of docs) {
    if (d.date === effHistoryDate) keysOnDate.add(d.path);
  }
  const out: { label: string; docKey: string }[] = [];
  if (keysOnDate.has('digest')) out.push({ label: 'Digest', docKey: 'digest' });
  const mte = `market-thesis-exploration/${effHistoryDate}.json`;
  if (keysOnDate.has(mte)) out.push({ label: 'Market thesis', docKey: mte });
  const tvm = `thesis-vehicle-map/${effHistoryDate}.json`;
  if (keysOnDate.has(tvm)) out.push({ label: 'Thesis vehicle map', docKey: tvm });
  for (const d of docs) {
    if (d.date !== effHistoryDate) continue;
    const p = (d.path || '').toLowerCase();
    if (p.includes('opportunity-screen') || p.includes('opportunity-screener')) {
      out.push({ label: 'Opportunity screener', docKey: d.path });
      break;
    }
  }
  return out;
}
