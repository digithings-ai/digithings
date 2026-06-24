import { describe, expect, it } from 'vitest';
import { formatUsd, formatTokens, cacheHitPct } from './run-economics-row';
import type { AtlasRunDiagnostics } from '@/lib/types';

function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
  return {
    run_id: 'r', run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
    started_at: null, finished_at: null, duration_s: null, llm_calls: 163,
    prompt_tokens: null, completion_tokens: null, total_tokens: 1_640_000, cached_tokens: 639_600,
    search_calls: null, grounding_ok: 31, grounding_failed: 0, est_cost_usd: 0.616,
    segments_total: 27, segments_ok: 27, segments_carried: 0, segments_failed: 0,
    error_summary: null, breakdown: null, created_at: '2026-06-23T16:58:51Z', ...o,
  };
}

describe('run-economics formatting', () => {
  it('formats cost to cents with a leading $', () => {
    expect(formatUsd(0.616)).toBe('$0.62');
  });
  it('renders null cost as an em-dash', () => {
    expect(formatUsd(null)).toBe('—');
  });
  it('abbreviates tokens to millions', () => {
    expect(formatTokens(1_640_000)).toBe('1.64M');
  });
  it('computes cache-hit pct from cached/total tokens', () => {
    expect(cacheHitPct(diag({}))).toBe(39);
  });
  it('returns null cache-hit when total tokens absent', () => {
    expect(cacheHitPct(diag({ total_tokens: null }))).toBeNull();
  });
});
