import { describe, expect, it } from 'vitest';
import type { RunEpisode } from './run-episodes';
import {
  buildWeekDaySlots,
  canGoToNextWeek,
  clampWeekStart,
  formatWeekRangeLabel,
  mondayOfWeek,
  shiftWeekStart,
  weekDates,
  weekdayShort,
} from './run-health-week';
import type { ResearchRunDiagnostics } from './types';

function episode(runDate: string, outcome: RunEpisode['outcome'] = 'ok'): RunEpisode {
  const latest = {
    run_id: `r-${runDate}`,
    run_type: 'delta',
    run_date: runDate,
    model: null,
    status: outcome === 'failed' ? 'failed' : 'ok',
    started_at: null,
    finished_at: `${runDate}T12:00:00Z`,
    duration_s: 100,
    llm_calls: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    cached_tokens: null,
    search_calls: null,
    grounding_ok: null,
    grounding_failed: null,
    est_cost_usd: null,
    segments_total: 27,
    segments_ok: 27,
    segments_carried: 0,
    segments_failed: 0,
    error_summary: null,
    breakdown: null,
    created_at: `${runDate}T12:00:00Z`,
  } satisfies ResearchRunDiagnostics;
  return {
    key: `${runDate}|delta`,
    runDate,
    runType: 'delta',
    attempts: 1,
    outcome,
    latest,
    errorSummary: null,
  };
}

describe('run-health-week', () => {
  it('resolves Monday as the start of the week (UTC)', () => {
    // 2026-08-27 is Thursday → week Mon Aug 24
    expect(mondayOfWeek('2026-08-27')).toBe('2026-08-24');
    expect(mondayOfWeek('2026-08-24')).toBe('2026-08-24');
    // Sunday belongs to the week that started the prior Monday
    expect(mondayOfWeek('2026-08-30')).toBe('2026-08-24');
    expect(mondayOfWeek('2026-08-23')).toBe('2026-08-17');
  });

  it('lists seven Mon→Sun dates for a week start', () => {
    expect(weekDates('2026-08-24')).toEqual([
      '2026-08-24',
      '2026-08-25',
      '2026-08-26',
      '2026-08-27',
      '2026-08-28',
      '2026-08-29',
      '2026-08-30',
    ]);
  });

  it('shifts by whole weeks', () => {
    expect(shiftWeekStart('2026-08-24', -1)).toBe('2026-08-17');
    expect(shiftWeekStart('2026-08-24', 1)).toBe('2026-08-31');
  });

  it('clamps week starts so the current week is the latest allowed', () => {
    const now = new Date('2026-08-27T15:00:00Z'); // week of Aug 24
    expect(clampWeekStart('2026-08-24', now)).toBe('2026-08-24');
    expect(clampWeekStart('2026-08-17', now)).toBe('2026-08-17');
    expect(clampWeekStart('2026-08-31', now)).toBe('2026-08-24');
    expect(clampWeekStart('2026-09-07', now)).toBe('2026-08-24');
  });

  it('allows next-week only when viewing a past week', () => {
    const now = new Date('2026-08-27T15:00:00Z');
    expect(canGoToNextWeek('2026-08-17', now)).toBe(true);
    expect(canGoToNextWeek('2026-08-24', now)).toBe(false);
    expect(canGoToNextWeek('2026-08-31', now)).toBe(false);
  });

  it('formats a compact week range label', () => {
    expect(formatWeekRangeLabel('2026-08-24')).toBe('Aug 24–30');
    expect(formatWeekRangeLabel('2026-08-31')).toBe('Aug 31–Sep 6');
  });

  it('maps weekday shorts Mon→Sun', () => {
    expect(weekdayShort('2026-08-24')).toBe('Mon');
    expect(weekdayShort('2026-08-30')).toBe('Sun');
  });

  it('fills empty day slots for days with no run yet', () => {
    const slots = buildWeekDaySlots(
      [episode('2026-08-25'), episode('2026-08-27', 'failed')],
      '2026-08-24'
    );
    expect(slots).toHaveLength(7);
    expect(slots.map((s) => s.date)).toEqual(weekDates('2026-08-24'));
    expect(slots[0].episode).toBeNull(); // Mon — empty
    expect(slots[1].episode?.runDate).toBe('2026-08-25');
    expect(slots[2].episode).toBeNull();
    expect(slots[3].episode?.outcome).toBe('failed');
    expect(slots.filter((s) => s.episode == null)).toHaveLength(5);
  });
});
