import { describe, it, expect } from 'vitest';
import { buildPipelineDayData } from './pipeline-graph-data';
import {
  REPRESENTATIVE_RUN_DOCUMENT_KEYS,
  classifyDocumentDiscovery,
  undiscoverablePresentKeys,
  unmappedRepresentativeDocumentKeys,
} from './pipeline-document-discoverability';
import { buildPipelineHref, stageForDocumentKey } from './pipeline-links';

describe('document-key discoverability (#2627)', () => {
  it('maps every representative-run key to a discovery path and stage', () => {
    expect(unmappedRepresentativeDocumentKeys()).toEqual([]);

    for (const key of REPRESENTATIVE_RUN_DOCUMENT_KEYS) {
      const discovery = classifyDocumentDiscovery(key);
      expect(discovery, key).not.toBeNull();
      expect(discovery!.stage).toBe(stageForDocumentKey(key));
      expect(['topology-leaf', 'topology-fanout', 'artifact-ledger']).toContain(discovery!.path);
    }
  });

  it('classifies topology leaves, fan-outs, and ledger-only siblings distinctly', () => {
    expect(classifyDocumentDiscovery('attention-plan')).toEqual({
      documentKey: 'attention-plan',
      path: 'topology-leaf',
      stage: 'inputs',
    });
    expect(classifyDocumentDiscovery('analyst/QQQ')).toEqual({
      documentKey: 'analyst/QQQ',
      path: 'topology-fanout',
      stage: 'selection',
    });
    expect(classifyDocumentDiscovery('document-deltas/macro')).toEqual({
      documentKey: 'document-deltas/macro',
      path: 'artifact-ledger',
      stage: 'research',
    });
    expect(classifyDocumentDiscovery('risk-debate')).toEqual({
      documentKey: 'risk-debate',
      path: 'artifact-ledger',
      stage: 'selection',
    });
    expect(classifyDocumentDiscovery('unknown-thing')).toBeNull();
  });

  it('keeps every present key on a representative day discoverable via artifacts + stage', () => {
    const day = buildPipelineDayData(
      REPRESENTATIVE_RUN_DOCUMENT_KEYS.map((document_key) => ({ document_key })),
    );

    expect(undiscoverablePresentKeys(day)).toEqual([]);
    expect(day.artifacts.map((a) => a.documentKey).sort()).toEqual(
      [...REPRESENTATIVE_RUN_DOCUMENT_KEYS].sort(),
    );

    for (const key of REPRESENTATIVE_RUN_DOCUMENT_KEYS) {
      const stage = stageForDocumentKey(key);
      expect(stage, key).not.toBeNull();
      expect(buildPipelineHref({ date: '2026-08-25', stage, node: key })).toContain(
        `node=${encodeURIComponent(key)}`,
      );
    }
  });
});
