import { describe, it, expect } from 'vitest';
import {
  buildPipelineHref,
  stageForDocumentKey,
  parsePipelineParams,
  leafDocumentKey,
  resolvePresentDigestKey,
} from './pipeline-links';
import { buildPipelineDayData } from './pipeline-graph-data';

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
    // Delta runs (the majority of days) publish `digest-delta`, not `digest` —
    // #1259 regression: the stage resolver must recognize both.
    expect(stageForDocumentKey('digest-delta')).toBe('synthesis');
    expect(stageForDocumentKey('analyst/IJR')).toBe('selection');
    expect(stageForDocumentKey('deliberation/EWT')).toBe('selection');
    expect(stageForDocumentKey('pm-rebalance')).toBe('selection');
    expect(stageForDocumentKey('risk-debate')).toBe('selection');
    expect(stageForDocumentKey('document-deltas/macro')).toBe('research');
    expect(stageForDocumentKey('sector-energy')).toBe('research');
    expect(stageForDocumentKey('commit-run/28041585974')).toBe('decision');
    expect(stageForDocumentKey('attention-plan')).toBe('inputs');
    expect(stageForDocumentKey('unknown-thing')).toBeNull();
  });
});

describe('resolvePresentDigestKey (#1259 — digest vs digest-delta drift)', () => {
  it('resolves to `digest` on a baseline day', () => {
    const day = buildPipelineDayData([{ document_key: 'digest' }, { document_key: 'macro' }]);
    expect(resolvePresentDigestKey(day)).toBe('digest');
  });
  it('resolves to `digest-delta` on a delta day', () => {
    const day = buildPipelineDayData([{ document_key: 'digest-delta' }, { document_key: 'macro' }]);
    expect(resolvePresentDigestKey(day)).toBe('digest-delta');
  });
  it('returns undefined when neither key is present', () => {
    const day = buildPipelineDayData([{ document_key: 'macro' }]);
    expect(resolvePresentDigestKey(day)).toBeUndefined();
  });
});

describe('pipeline link resolvers', () => {
  it('parses the locked grammar', () => {
    const p = parsePipelineParams(new URLSearchParams('date=2026-06-23&stage=selection&node=analyst/SPY'));
    expect(p).toEqual({ date: '2026-06-23', stage: 'selection', node: 'analyst/SPY' });
  });
  it('maps sub-steps to document_keys', () => {
    expect(leafDocumentKey('attention-plan')).toBe('attention-plan');
    expect(leafDocumentKey('preflight')).toBe('inputs');
    expect(leafDocumentKey('consolidate')).toBe('bias-row');
    expect(leafDocumentKey('thesis')).toBe('thesis/thesis-review');
    expect(leafDocumentKey('screener')).toBe('opportunity-screener');
    expect(leafDocumentKey('pm-direction')).toBe('pm-direction-memo');
    expect(leafDocumentKey('analysts', 'SPY')).toBe('analyst/SPY');
    expect(leafDocumentKey('nope')).toBeNull();
  });
  it('maps inspectable WP-B keys to their pipeline stages', () => {
    expect(stageForDocumentKey('inputs')).toBe('inputs');
    expect(stageForDocumentKey('bias-row')).toBe('synthesis');
    expect(stageForDocumentKey('thesis/thesis-review')).toBe('selection');
    expect(stageForDocumentKey('opportunity-screener')).toBe('selection');
  });
});
