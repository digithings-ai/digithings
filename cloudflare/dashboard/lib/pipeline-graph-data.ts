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
  /** True when daily_snapshots records a run, even if no documents were published. */
  runRecorded?: boolean;
  /** count of present document_keys per fan-out id (= fanoutKeys length; omitted when 0) */
  fanoutCounts: Record<string, number>;
  /** sorted list of this day's real document_keys per fan-out id */
  fanoutKeys: Record<string, string[]>;
  presentKeys: Set<string>;
  artifacts: PipelineArtifact[];
}

export interface PipelineArtifact {
  documentKey: string;
  title: string | null;
  docType: string | null;
  phase: string | null;
  category: string | null;
  segment: string | null;
  sector: string | null;
  runType: string | null;
}

export interface PipelineDocumentRow {
  document_key: string;
  title?: string | null;
  doc_type?: string | null;
  phase?: string | null;
  category?: string | null;
  segment?: string | null;
  sector?: string | null;
  run_type?: string | null;
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

export function buildPipelineDayData(docs: PipelineDocumentRow[]): PipelineDayData {
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

  const artifacts = docs
    .map((doc) => ({
      documentKey: doc.document_key,
      title: doc.title ?? null,
      docType: doc.doc_type ?? null,
      phase: doc.phase ?? null,
      category: doc.category ?? null,
      segment: doc.segment ?? null,
      sector: doc.sector ?? null,
      runType: doc.run_type ?? null,
    }))
    .sort((left, right) => left.documentKey.localeCompare(right.documentKey));

  return {
    runRecorded: docs.length > 0,
    fanoutCounts,
    fanoutKeys,
    presentKeys,
    artifacts,
  };
}
