/**
 * Glass-box discoverability (#2627 / #1945): every persisted document_key for a
 * representative run must be reachable from Pipeline via a topology leaf,
 * fan-out branch, or the All artifacts ledger — never an opaque unmapped key.
 */

import { fanoutIdForKey, type PipelineDayData } from './pipeline-graph-data';
import {
  DIGEST_DOCUMENT_KEYS,
  stageForDocumentKey,
  type PipelineStage,
} from './pipeline-links';

export type DocumentDiscoveryPath = 'topology-leaf' | 'topology-fanout' | 'artifact-ledger';

export interface DocumentDiscovery {
  documentKey: string;
  path: DocumentDiscoveryPath;
  stage: PipelineStage;
}

/**
 * Representative Atlas + Hermes run keys: topology leaves, one sample per
 * fan-out family, and known ledger-only siblings (deltas, risk-debate).
 * Absence of a key on a real day is fine; classification must still succeed.
 */
export const REPRESENTATIVE_RUN_DOCUMENT_KEYS: readonly string[] = [
  'inputs',
  'attention-plan',
  'macro',
  'alt-cta-positioning',
  'inst-hedge-fund-intel',
  'bonds',
  'sector-technology',
  'document-deltas/macro',
  'bias-row',
  'digest',
  'digest-delta',
  'thesis/thesis-review',
  'opportunity-screener',
  'analyst/QQQ',
  'deliberation/QQQ',
  'risk-debate',
  'pm-direction-memo',
  'pm-rebalance',
  'commit-run/1234567890',
  'beliefs',
];

const TOPOLOGY_LEAF_KEYS = new Set<string>([
  'inputs',
  'attention-plan',
  'macro',
  'bias-row',
  ...DIGEST_DOCUMENT_KEYS,
  'thesis/thesis-review',
  'opportunity-screener',
  'pm-direction-memo',
  'pm-rebalance',
  'beliefs',
]);

function isTopologyLeafKey(documentKey: string): boolean {
  return TOPOLOGY_LEAF_KEYS.has(documentKey.toLowerCase());
}

/**
 * Classify how Pipeline surfaces a document_key. Returns null when the key is
 * unknown — those must not appear in a representative-run fixture.
 */
export function classifyDocumentDiscovery(documentKey: string): DocumentDiscovery | null {
  const stage = stageForDocumentKey(documentKey);
  if (!stage) return null;

  if (fanoutIdForKey(documentKey)) {
    return { documentKey, path: 'topology-fanout', stage };
  }
  if (isTopologyLeafKey(documentKey)) {
    return { documentKey, path: 'topology-leaf', stage };
  }
  return { documentKey, path: 'artifact-ledger', stage };
}

/** Keys from the representative fixture that still fail classification. */
export function unmappedRepresentativeDocumentKeys(): string[] {
  return REPRESENTATIVE_RUN_DOCUMENT_KEYS.filter((key) => classifyDocumentDiscovery(key) === null);
}

/**
 * Keys present on a day that are not discoverable (no stage / path). By
 * construction `buildPipelineDayData` puts every row into `artifacts`; this
 * catches stage-mapping gaps for live or fixture days.
 */
export function undiscoverablePresentKeys(day: PipelineDayData): string[] {
  return [...day.presentKeys].filter((key) => classifyDocumentDiscovery(key) === null).sort();
}
