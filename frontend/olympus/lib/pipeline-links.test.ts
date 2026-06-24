import { describe, it, expect } from 'vitest';
import { buildPipelineHref, stageForDocumentKey } from './pipeline-links';

describe('buildPipelineHref (LOCKED deep-link grammar)', () => {
  it('emits /pipeline?date=&stage=&node= keyed off document_key', () => {
    expect(buildPipelineHref({ date: '2026-06-23', stage: 'selection', node: 'analyst/IJR' }))
      .toBe('/pipeline?date=2026-06-23&stage=selection&node=analyst%2FIJR');
  });
  it('omits empty params and url-encodes the node key', () => {
    expect(buildPipelineHref({ date: '2026-06-23', node: 'digest' }))
      .toBe('/pipeline?date=2026-06-23&node=digest');
    expect(buildPipelineHref({})).toBe('/pipeline');
  });
  it('infers stage from a document_key when the caller has none', () => {
    expect(stageForDocumentKey('digest')).toBe('synthesis');
    expect(stageForDocumentKey('analyst/IJR')).toBe('selection');
    expect(stageForDocumentKey('deliberation/EWT')).toBe('selection');
    expect(stageForDocumentKey('pm-rebalance')).toBe('selection');
    expect(stageForDocumentKey('sector-energy')).toBe('research');
    expect(stageForDocumentKey('commit-run/28041585974')).toBe('decision');
    expect(stageForDocumentKey('unknown-thing')).toBeNull();
  });
});
