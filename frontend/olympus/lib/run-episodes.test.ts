import { describe, expect, it } from 'vitest';
import { groupRunEpisodes } from './run-episodes';
import type { AtlasRunDiagnostics } from './types';

function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
  return {
    run_id: 'r', attempt: null, run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
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

  // #1762: in-workflow retries share GITHUB_RUN_ID and used to upsert on it alone, so three
  // attempts collapsed into ONE row — `attempts` read 1 and `recovered` was unreachable. Per
  // migration 065 each attempt is its own row, keyed (run_id, attempt).
  describe('in-workflow retries (#1762)', () => {
    it('counts three attempts of one workflow run as three attempts of one episode', () => {
      const eps = groupRunEpisodes([
        diag({ run_id: '29688378908', attempt: 3, status: 'ok' }),
        diag({ run_id: '29688378908', attempt: 1, status: 'failed' }),
        diag({ run_id: '29688378908', attempt: 2, status: 'degraded' }),
      ]);
      expect(eps).toHaveLength(1);
      expect(eps[0].attempts).toBe(3);
      expect(eps[0].outcome).toBe('recovered');
    });

    it('orders by attempt, not by created_at, so a tied timestamp cannot invert the episode', () => {
      // Two attempts of one job can share a created_at to the millisecond; before 065 the
      // surviving row's created_at was the FIRST attempt's insert while its other columns were
      // the last attempt's. The counter is exact, the timestamp is a proxy.
      const eps = groupRunEpisodes([
        diag({ run_id: 'r', attempt: 2, status: 'ok', created_at: '2026-07-19T13:30:21Z' }),
        diag({ run_id: 'r', attempt: 1, status: 'failed', created_at: '2026-07-19T13:30:21Z' }),
      ]);
      expect(eps[0].latest.status).toBe('ok'); // attempt 2 is the outcome
      expect(eps[0].outcome).toBe('recovered'); // attempt 1's failure is not lost
    });

    it('falls back to created_at for legacy rows that carry the 0 sentinel', () => {
      // Migration 065 stamped every pre-existing row 0 rather than fabricating 1, so ordering
      // has to keep working without a usable counter.
      const eps = groupRunEpisodes([
        diag({ run_id: 'a', attempt: 0, status: 'ok', created_at: '2026-06-23T16:43:00Z' }),
        diag({ run_id: 'b', attempt: 0, status: 'failed', created_at: '2026-06-23T16:34:00Z' }),
      ]);
      expect(eps[0].attempts).toBe(2);
      expect(eps[0].outcome).toBe('recovered');
      expect(eps[0].latest.run_id).toBe('a');
    });

    it('does not treat the 0 sentinel as a real attempt number when mixed with real ones', () => {
      // A date spanning the migration: the legacy row must sort by timestamp rather than
      // claiming to be attempt 0 and therefore "before" attempt 1.
      const eps = groupRunEpisodes([
        diag({ run_id: 'new', attempt: 1, status: 'ok', created_at: '2026-08-05T22:10:00Z' }),
        diag({ run_id: 'old', attempt: 0, status: 'failed', created_at: '2026-08-05T22:00:00Z' }),
      ]);
      expect(eps[0].latest.run_id).toBe('new');
      expect(eps[0].attempts).toBe(2);
    });
  });
});
