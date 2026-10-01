import { describe, expect, it } from 'vitest';
import { applyPipelineScope, scopeFilter, PIPELINE_SCOPED_TABLES } from './pipeline-scope';

function fakeQuery() {
  const calls: Array<[string, unknown]> = [];
  const q = {
    calls,
    eq(c: string, v: unknown) {
      calls.push([c, v]);
      return q;
    },
  };
  return q;
}

describe('pipeline scope', () => {
  it('is a no-op for baseline and when scope is omitted', () => {
    const q = fakeQuery();
    applyPipelineScope(q, 'documents');
    applyPipelineScope(q, 'documents', { pipelineId: 'baseline' });
    expect(q.calls).toEqual([]);
  });

  it('is a no-op for a non-baseline scope while no table carries pipeline_id', () => {
    expect(PIPELINE_SCOPED_TABLES.size).toBe(0);
    expect(scopeFilter('documents', { pipelineId: 'fork-1' })).toBeNull();
  });

  it('adds pipeline_id once a table is registered', () => {
    PIPELINE_SCOPED_TABLES.add('documents');
    try {
      const q = fakeQuery();
      applyPipelineScope(q, 'documents', { pipelineId: 'fork-1' });
      expect(q.calls).toEqual([['pipeline_id', 'fork-1']]);
      expect(scopeFilter('documents', { pipelineId: 'baseline' })).toBeNull();
    } finally {
      PIPELINE_SCOPED_TABLES.delete('documents');
    }
  });
});
