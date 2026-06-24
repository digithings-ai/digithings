const PREFIX_COUNTERS: { fanoutId: string; match: (k: string) => boolean }[] = [
  { fanoutId: 'alt-data', match: (k) => k.startsWith('alt-') },
  { fanoutId: 'institutional', match: (k) => k.startsWith('inst-') },
  { fanoutId: 'sectors', match: (k) => k.startsWith('sector-') && k !== 'sector-scorecard' },
  { fanoutId: 'analysts', match: (k) => k.startsWith('analyst/') },
  { fanoutId: 'deliberation', match: (k) => k.startsWith('deliberation/') },
];

export interface PipelineDayData { fanoutCounts: Record<string, number>; presentKeys: Set<string>; }

export function buildPipelineDayData(docs: { document_key: string }[]): PipelineDayData {
  const fanoutCounts: Record<string, number> = {};
  const presentKeys = new Set<string>();
  for (const { document_key } of docs) {
    presentKeys.add(document_key);
    for (const c of PREFIX_COUNTERS) {
      if (c.match(document_key)) fanoutCounts[c.fanoutId] = (fanoutCounts[c.fanoutId] ?? 0) + 1;
    }
  }
  return { fanoutCounts, presentKeys };
}
