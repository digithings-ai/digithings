import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FreshnessBanner, latestSuccessfulRun } from './freshness-banner';
import type { AtlasRunDiagnostics } from '@/lib/types';

function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
  return {
    run_id: 'r', run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
    started_at: null, finished_at: '2026-06-23T16:58:51Z', duration_s: null,
    llm_calls: null, prompt_tokens: null, completion_tokens: null, total_tokens: null,
    cached_tokens: null, search_calls: null, grounding_ok: null, grounding_failed: null,
    est_cost_usd: null, segments_total: 27, segments_ok: 27, segments_carried: 0,
    segments_failed: 0, error_summary: null, breakdown: null, created_at: '2026-06-23T16:58:51Z',
    ...o,
  };
}

describe('latestSuccessfulRun', () => {
  it('skips a newer failed row and returns the ok run', () => {
    const rows = [diag({ run_id: 'fail', status: 'failed', created_at: '2026-06-23T17:10:00Z' }), diag({ run_id: 'ok' })];
    expect(latestSuccessfulRun(rows)?.run_id).toBe('ok');
  });
  it('returns null when no run succeeded', () => {
    expect(latestSuccessfulRun([diag({ status: 'failed' })])).toBeNull();
  });
});

describe('FreshnessBanner', () => {
  it('narrates last successful run with run type and segment count', () => {
    const html = renderToStaticMarkup(createElement(FreshnessBanner, { latest: diag({}) }));
    expect(html).toContain('Last successful run');
    expect(html).toContain('baseline');
    expect(html).toContain('27/27');
  });
});
