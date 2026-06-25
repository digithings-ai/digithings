const ASSET_CLASSES = new Set(['bonds', 'commodities', 'crypto', 'equity', 'forex', 'international']);

const FANOUT_MATCHERS: { fanoutId: string; match: (k: string) => boolean }[] = [
  { fanoutId: 'alt-data', match: (k) => k.startsWith('alt-') },
  { fanoutId: 'institutional', match: (k) => k.startsWith('inst-') },
  { fanoutId: 'asset-classes', match: (k) => ASSET_CLASSES.has(k) },
  { fanoutId: 'sectors', match: (k) => k.startsWith('sector-') && k !== 'sector-scorecard' },
  { fanoutId: 'analysts', match: (k) => k.startsWith('analyst/') },
  { fanoutId: 'deliberation', match: (k) => k.startsWith('deliberation/') },
];

export interface PipelineDayData {
  /** count of present document_keys per fan-out id (= fanoutKeys length; omitted when 0) */
  fanoutCounts: Record<string, number>;
  /** sorted list of this day's real document_keys per fan-out id */
  fanoutKeys: Record<string, string[]>;
  presentKeys: Set<string>;
}

/**
 * Map a document_key to the fan-out id it belongs to (e.g. `analyst/QQQ` -> `analysts`,
 * `sector-tech` -> `sectors`, `bonds` -> `asset-classes`), or null for non-fan-out keys.
 * Used to auto-expand the owning fan-out when deep-linking straight to a branch node.
 */
export function fanoutIdForKey(key: string): string | null {
  for (const c of FANOUT_MATCHERS) {
    if (c.match(key)) return c.fanoutId;
  }
  return null;
}

export function buildPipelineDayData(docs: { document_key: string }[]): PipelineDayData {
  const presentKeys = new Set<string>();
  const fanoutKeys: Record<string, string[]> = {};
  for (const { fanoutId } of FANOUT_MATCHERS) fanoutKeys[fanoutId] = [];

  for (const { document_key } of docs) {
    presentKeys.add(document_key);
    for (const c of FANOUT_MATCHERS) {
      if (c.match(document_key)) fanoutKeys[c.fanoutId].push(document_key);
    }
  }

  const fanoutCounts: Record<string, number> = {};
  for (const { fanoutId } of FANOUT_MATCHERS) {
    fanoutKeys[fanoutId].sort();
    if (fanoutKeys[fanoutId].length > 0) fanoutCounts[fanoutId] = fanoutKeys[fanoutId].length;
  }

  return { fanoutCounts, fanoutKeys, presentKeys };
}
