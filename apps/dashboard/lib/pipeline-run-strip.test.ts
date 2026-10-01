import { describe, expect, it } from 'vitest';
import { addDays, buildRunStrip, summariseRunStrip, worstEpisode } from './pipeline-run-strip';
import type { RunEpisode } from './run-episodes';

function ep(runDate: string, outcome: RunEpisode['outcome'], attempts = 1, runType = 'baseline', latest: Partial<RunEpisode['latest']> = {}): RunEpisode {
  return { key: `${runDate}|${runType}`, runDate, runType, attempts, outcome, latest: latest as RunEpisode['latest'], errorSummary: null };
}

describe('pipeline-run-strip', () => {
  it('addDays crosses month boundaries in UTC', () => {
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
    expect(addDays('2026-12-31', 1)).toBe('2027-01-01');
  });

  it('builds 30 chronological cells ending at `end`', () => {
    const cells = buildRunStrip({ runDates: [], episodes: [], end: '2026-09-30' });
    expect(cells).toHaveLength(30);
    expect(cells[29].date).toBe('2026-09-30');
    expect(cells[0].date).toBe('2026-09-01');
    expect(cells.every((c) => c.tone === 'idle' && c.outcome === null)).toBe(true);
  });

  it('maps outcomes to health tones (never up/down) and tags no-telemetry', () => {
    const cells = buildRunStrip({
      runDates: ['2026-09-28', '2026-09-29', '2026-09-30'],
      episodes: [ep('2026-09-29', 'ok'), ep('2026-09-30', 'failed', 3)],
      end: '2026-09-30',
      days: 3,
    });
    expect(cells.map((c) => c.tone)).toEqual(['off', 'ok', 'warn']);
    expect(cells.map((c) => c.kind)).toEqual(['no-telemetry', 'complete', 'failed']);
    expect(cells[2].label).toContain('3 attempts');
    expect(cells[1].label).not.toContain('attempt');
  });

  it('takes the worst episode when a day has a baseline and a delta run', () => {
    expect(worstEpisode([ep('d', 'ok'), ep('d', 'degraded', 1, 'delta')])?.outcome).toBe('degraded');
    expect(worstEpisode([])).toBeNull();
  });

  it('summarises healthy vs attention days', () => {
    const cells = buildRunStrip({
      runDates: ['2026-09-29', '2026-09-30'],
      episodes: [ep('2026-09-29', 'ok'), ep('2026-09-30', 'recovered', 2)],
      end: '2026-09-30',
      days: 3,
    });
    expect(summariseRunStrip(cells)).toEqual({ runs: 2, healthy: 1, attention: 1, carried: 0 });
  });

  it('reads a carry-only day as ok (accent), matching the Brief, and not as attention', () => {
    const carry = ep('2026-09-30', 'degraded', 1, 'delta', { status: 'degraded', segments_carried: 4, segments_failed: 0 });
    const cells = buildRunStrip({ runDates: ['2026-09-30'], episodes: [carry], end: '2026-09-30', days: 1 });
    expect(cells[0].kind).toBe('complete-with-carry');
    expect(cells[0].tone).toBe('ok');
    expect(cells[0].label).toBe('2026-09-30: complete with carry');
    expect(summariseRunStrip(cells)).toEqual({ runs: 1, healthy: 0, attention: 0, carried: 1 });
  });

  it('a retried day and a failed day are warn; failed outranks a carry run on the same date', () => {
    const cells = buildRunStrip({
      runDates: ['2026-09-29', '2026-09-30'],
      episodes: [
        ep('2026-09-29', 'recovered', 2, 'baseline', { status: 'ok' }),
        ep('2026-09-30', 'degraded', 1, 'delta', { status: 'degraded', segments_carried: 2 }),
        ep('2026-09-30', 'failed', 1, 'baseline', { status: 'failed' }),
      ],
      end: '2026-09-30',
      days: 2,
    });
    expect(cells.map((c) => [c.kind, c.tone])).toEqual([['attention', 'warn'], ['failed', 'warn']]);
  });
});
