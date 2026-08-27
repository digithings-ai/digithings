/**
 * Monday-start week window helpers for the Brief Pipeline Health run bar.
 * Dates are calendar YYYY-MM-DD in UTC (matching `run_date` storage).
 */

import type { RunEpisode } from './run-episodes';

const WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

export function parseYmd(ymd: string): Date {
  const [y, m, d] = ymd.split('-').map(Number);
  if (!y || !m || !d) throw new Error(`Invalid YYYY-MM-DD: ${ymd}`);
  return new Date(Date.UTC(y, m - 1, d));
}

export function formatYmd(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** Monday (UTC) of the week containing `ymd` or a Date. */
export function mondayOfWeek(ymdOrDate: string | Date): string {
  const d =
    typeof ymdOrDate === 'string'
      ? parseYmd(ymdOrDate)
      : new Date(Date.UTC(ymdOrDate.getUTCFullYear(), ymdOrDate.getUTCMonth(), ymdOrDate.getUTCDate()));
  const day = d.getUTCDay(); // 0 = Sun … 6 = Sat
  const offset = day === 0 ? -6 : 1 - day;
  d.setUTCDate(d.getUTCDate() + offset);
  return formatYmd(d);
}

/** Seven YYYY-MM-DD strings Mon→Sun for a Monday week start. */
export function weekDates(weekStartMonday: string): string[] {
  const start = parseYmd(weekStartMonday);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + i);
    return formatYmd(d);
  });
}

export function shiftWeekStart(weekStartMonday: string, deltaWeeks: number): string {
  const d = parseYmd(weekStartMonday);
  d.setUTCDate(d.getUTCDate() + deltaWeeks * 7);
  return formatYmd(d);
}

export function weekdayShort(ymd: string): string {
  const day = parseYmd(ymd).getUTCDay();
  // Map Sun=0 → index 6; Mon=1 → 0 …
  return WEEKDAY_SHORT[day === 0 ? 6 : day - 1];
}

const MONTH_SHORT = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

function dayLabel(ymd: string): { month: string; day: number } {
  const d = parseYmd(ymd);
  return { month: MONTH_SHORT[d.getUTCMonth()], day: d.getUTCDate() };
}

/** Compact range label, e.g. "Aug 24–30" or "Aug 31–Sep 6". */
export function formatWeekRangeLabel(weekStartMonday: string): string {
  const days = weekDates(weekStartMonday);
  const first = dayLabel(days[0]);
  const last = dayLabel(days[6]);
  if (first.month === last.month) {
    return `${first.month} ${first.day}–${last.day}`;
  }
  return `${first.month} ${first.day}–${last.month} ${last.day}`;
}

/** Newest episode wins per run_date (episodes should already be newest-first). */
export function episodeByRunDate(episodes: RunEpisode[]): Map<string, RunEpisode> {
  const map = new Map<string, RunEpisode>();
  for (const ep of episodes) {
    if (!ep.runDate || map.has(ep.runDate)) continue;
    map.set(ep.runDate, ep);
  }
  return map;
}

export type WeekDaySlot = {
  date: string;
  weekday: string;
  episode: RunEpisode | null;
};

/** Seven day slots for a week — empty `episode` when no run yet. */
export function buildWeekDaySlots(
  episodes: RunEpisode[],
  weekStartMonday: string
): WeekDaySlot[] {
  const byDate = episodeByRunDate(episodes);
  return weekDates(weekStartMonday).map((date) => ({
    date,
    weekday: weekdayShort(date),
    episode: byDate.get(date) ?? null,
  }));
}
