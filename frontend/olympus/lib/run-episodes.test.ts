import { describe, expect, it } from 'vitest';
import { groupRunEpisodes } from './run-episodes';
import type { AtlasRunDiagnostics } from './types';

function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
  return {
    run_id: 'r', run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
    started_at: null, finished_at: null, duration_s: null, llm_calls: null,
    prompt_tokens: null, completion_tokens: null, total_tokens: null, cached_tokens: null,
    search_calls: null, grounding_ok: null, grounding_failed: null, est_cost_usd: null,
    segments_total: 27, segments_ok: 27, segments_carried: 0, segments_failed: 0,
    error_summary: null, breakdown: null, created_at: '2026-06-23T16:43:00Z', ...o,
  };
}

describe('groupRunEpisodes', () => {
  it('collapses a failed→ok pair on the same date+type into one recovered episode', () => {
    const rows = [
      diag({ run_id: 'ok', status: 'ok', created_at: '2026-06-23T16:43:00Z' }),
      diag({ run_id: 'fail', status: 'failed', created_at: '2026-06-23T16:34:00Z',
        error_summary: 'chain/hermes: ON CONFLICT' }),
    ];
    const eps = groupRunEpisodes(rows);
    expect(eps).toHaveLength(1);
    expect(eps[0].attempts).toBe(2);
    expect(eps[0].outcome).toBe('recovered');
    expect(eps[0].runDate).toBe('2026-06-23');
  });

  it('keeps distinct date+type pairs as separate episodes', () => {
    const eps = groupRunEpisodes([
      diag({ run_id: 'a', run_date: '2026-06-24', run_type: 'delta', status: 'degraded' }),
      diag({ run_id: 'b', run_date: '2026-06-23', run_type: 'baseline', status: 'ok' }),
    ]);
    expect(eps).toHaveLength(2);
    expect(eps[0].outcome).toBe('degraded'); // newest episode first
  });

  it('marks an all-failed episode as failed', () => {
    const eps = groupRunEpisodes([diag({ status: 'failed' })]);
    expect(eps[0].outcome).toBe('failed');
  });
});
