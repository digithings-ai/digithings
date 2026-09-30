import { describe, expect, it } from 'vitest';
import { buildDayKpis, formatDeltaPct, median } from './pipeline-kpis';
import type { RunEpisode } from './run-episodes';
import type { ResearchRunDiagnostics } from './types';

function ep(date: string, duration: number | null, over: Partial<ResearchRunDiagnostics> = {}, attempts = 1, runType = 'b'): RunEpisode {
  const latest = {
    run_date: date,
    duration_s: duration,
    status: 'ok',
    segments_ok: 12,
    segments_total: 14,
    segments_carried: 1,
    segments_failed: 1,
    breakdown: null,
    ...over,
  } as ResearchRunDiagnostics;
  return { key: `${date}|${runType}`, runDate: date, runType, attempts, outcome: 'ok', latest, errorSummary: null };
}

describe('pipeline-kpis', () => {
  it('median handles empty, odd and even', () => {
    expect(median([])).toBeNull();
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 2, 3])).toBe(2.5);
  });

  it('returns em-dash-ready nulls when the date has no telemetry', () => {
    const k = buildDayKpis({ date: '2026-09-30', episodes: [], artifactCount: 7 });
    expect(k.hasTelemetry).toBe(false);
    expect(k.durationS).toBeNull();
    expect(k.segments.total).toBeNull();
    expect(k.artifacts).toBe(7);
    expect(k.durationSeries).toHaveLength(30);
  });

  it('gates the duration delta on >= 5 prior days', () => {
    const few = [1, 2, 3, 4].map((i) => ep(`2026-09-${20 + i}`, 100));
    expect(buildDayKpis({ date: '2026-09-30', episodes: [...few, ep('2026-09-30', 150)], artifactCount: 0 }).durationDeltaPct).toBeNull();
    const enough = [1, 2, 3, 4, 5].map((i) => ep(`2026-09-${20 + i}`, 100));
    const k = buildDayKpis({ date: '2026-09-30', episodes: [...enough, ep('2026-09-30', 150)], artifactCount: 0 });
    expect(k.durationDeltaPct).toBe(50);
    expect(formatDeltaPct(k.durationDeltaPct)).toBe('+50% vs median');
  });

  it('compares a delta run only against prior runs of the same run_type', () => {
    const fullRuns = [1, 2, 3, 4, 5, 6].map((i) => ep(`2026-09-${20 + i}`, 1000, {}, 1, 'baseline'));
    const delta = ep('2026-09-30', 50, {}, 1, 'delta');
    // Against full runs the delta would read -95%: it must be hidden instead.
    const mixed = buildDayKpis({ date: '2026-09-30', episodes: [...fullRuns, delta], artifactCount: 0 });
    expect(mixed.durationS).toBe(50);
    expect(mixed.durationDeltaPct).toBeNull();
    expect(mixed.runType).toBe('delta');
    // Same-type priors below the floor: still hidden, even with many other-type days.
    const fourDeltas = [1, 2, 3, 4].map((i) => ep(`2026-09-${10 + i}`, 40, {}, 1, 'delta'));
    expect(buildDayKpis({ date: '2026-09-30', episodes: [...fullRuns, ...fourDeltas, delta], artifactCount: 0 }).durationDeltaPct).toBeNull();
    // >= 5 same-type priors: computed against those only (median 40 -> +25%).
    const fiveDeltas = [1, 2, 3, 4, 5].map((i) => ep(`2026-09-${10 + i}`, 40, {}, 1, 'delta'));
    expect(buildDayKpis({ date: '2026-09-30', episodes: [...fullRuns, ...fiveDeltas, delta], artifactCount: 0 }).durationDeltaPct).toBe(25);
  });

  it('classifies the day with the shared status vocabulary (carry alone is not a problem)', () => {
    const carry = buildDayKpis({ date: '2026-09-30', episodes: [ep('2026-09-30', 60, { segments_failed: 0, status: 'degraded' })], artifactCount: 0 });
    expect(carry.kind).toBe('complete-with-carry');
    const bad = buildDayKpis({ date: '2026-09-30', episodes: [ep('2026-09-30', 60)], artifactCount: 0 });
    expect(bad.kind).toBe('failed');
    expect(buildDayKpis({ date: '2026-09-30', episodes: [], artifactCount: 0 }).kind).toBe('no-telemetry');
  });

  it('reports unknown attempts (0) as null, never 1, and leaves gaps for missing days', () => {
    const k = buildDayKpis({ date: '2026-09-30', episodes: [ep('2026-09-30', 60, {}, 0)], artifactCount: 0 });
    expect(k.attempts).toBeNull();
    expect(k.durationSeries[29]).toBe(60);
    expect(k.durationSeries[28]).toBeNull();
  });

  it('parses phase health from the breakdown when present', () => {
    const k = buildDayKpis({
      date: '2026-09-30',
      episodes: [ep('2026-09-30', 60, { breakdown: { phase1_outputs: { ok: 3, failed: 1, carried: 0 } } })],
      artifactCount: 0,
    });
    expect(k.phases).toEqual([{ phase: 1, ok: 3, failed: 1, carried: 0 }]);
  });
});
