/**
 * Pure derivations for settings status strips: overlay job runs, notification
 * sends, hop-proof progress, next scheduled day, plan ladder. Health tones
 * only (ok = accent, warn, off = ink-mute, idle = hollow); never up/down.
 */
import type { JobRunView, NotificationLogEvent } from '@/lib/settings-api';
import type { StatusCell, StatusTone } from '@digithings/ui/ui';
import {
  STAGES,
  WEEKDAYS,
  type PipelineScheduleState,
  type StageName,
  type WeekdayName,
} from '@/lib/settings/pipeline-schedule';
import type { PlanTier } from '@/lib/entitlements';

function ms(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : null;
}

export function jobDurationMs(job: Pick<JobRunView, 'started_at' | 'finished_at'>): number | null {
  const a = ms(job.started_at);
  const b = ms(job.finished_at);
  return a !== null && b !== null && b >= a ? b - a : null;
}

export function formatDuration(d: number | null): string {
  if (d === null) return 'duration unknown';
  if (d < 1000) return `${d}ms`;
  const s = Math.round(d / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function jobTone(status: string): StatusTone {
  const s = status.toLowerCase();
  if (s === 'succeeded') return 'ok';
  if (s === 'failed' || s === 'error') return 'warn';
  return 'off';
}

export type RunsStrip = {
  cells: StatusCell[];
  summary: string;
  ok: number;
  total: number;
};

/** Last `limit` jobs, oldest to newest left to right. */
export function jobsToStrip(jobs: readonly JobRunView[], limit = 20): RunsStrip {
  const ordered = jobs
    .slice()
    .sort((a, b) => (ms(a.started_at) ?? 0) - (ms(b.started_at) ?? 0))
    .slice(-limit);
  const cells: StatusCell[] = ordered.map((j) => ({
    key: j.id,
    tone: jobTone(j.status),
    label: `${j.job_type} ${j.status}, ${formatDuration(jobDurationMs(j))}${
      j.error ? `, ${j.error}` : ''
    }${j.started_at ? `, ${j.started_at}` : ''}`,
  }));
  const ok = ordered.filter((j) => j.status === 'succeeded').length;
  return {
    cells,
    ok,
    total: ordered.length,
    summary:
      ordered.length === 0
        ? 'No overlay runs yet'
        : `${ok} of ${ordered.length} recent overlay runs succeeded`,
  };
}

function isoDay(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}

/** One cell per UTC day for `days` days ending `now`; ok when a send landed. */
export function notificationStrip(
  events: readonly Pick<NotificationLogEvent, 'sent_date'>[],
  now: number = Date.now(),
  days = 30,
): { cells: StatusCell[]; summary: string; sends: number } {
  const counts = new Map<string, number>();
  for (const e of events) {
    const d = (e.sent_date ?? '').slice(0, 10);
    if (d) counts.set(d, (counts.get(d) ?? 0) + 1);
  }
  const cells: StatusCell[] = [];
  let sends = 0;
  for (let i = days - 1; i >= 0; i--) {
    const day = isoDay(now - i * 86_400_000);
    const n = counts.get(day) ?? 0;
    sends += n;
    cells.push({
      key: day,
      tone: n > 0 ? 'ok' : 'idle',
      label: n > 0 ? `${day}: ${n} sent` : `${day}: none sent`,
    });
  }
  return {
    cells,
    sends,
    summary: `${sends} digest or alert ${sends === 1 ? 'send' : 'sends'} in the last ${days} days`,
  };
}

export type HopLike = { key: string; label: string; proven: boolean; blocker?: string | null };

/** Proven = ok, blocked = warn, unproven without a known blocker = off. */
export function hopsToStrip(hops: readonly HopLike[]): {
  cells: StatusCell[];
  proven: number;
  total: number;
  summary: string;
} {
  const proven = hops.filter((h) => h.proven).length;
  return {
    cells: hops.map((h) => ({
      key: h.key,
      tone: h.proven ? 'ok' : h.blocker ? 'warn' : 'off',
      label: `${h.label}: ${h.proven ? 'proven' : h.blocker ? `blocked, ${h.blocker}` : 'unproven'}`,
    })),
    proven,
    total: hops.length,
    summary: `${proven} of ${hops.length} remaining hops proven`,
  };
}

const JS_DAY_TO_WEEKDAY: readonly WeekdayName[] = [
  'sunday',
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
];

/**
 * First weekday (starting today, UTC) with at least one stage enabled. Day-level
 * only: the schedule carries no time of day, and the venue calendar still vetoes
 * execution. Null when the whole week is off.
 */
export function nextScheduledDay(
  schedule: PipelineScheduleState,
  now: number = Date.now(),
): { day: WeekdayName; stages: StageName[]; offset: number } | null {
  const today = new Date(now).getUTCDay();
  for (let offset = 0; offset < 7; offset++) {
    const day = JS_DAY_TO_WEEKDAY[(today + offset) % 7];
    const stages = STAGES.filter((s) => schedule[day][s]);
    if (stages.length > 0) return { day, stages, offset };
  }
  return null;
}

/** "14 of 21 stage slots enabled". */
export function scheduleSummary(schedule: PipelineScheduleState): string {
  let on = 0;
  for (const d of WEEKDAYS) for (const s of STAGES) if (schedule[d][s]) on++;
  return `${on} of ${WEEKDAYS.length * STAGES.length} stage slots enabled`;
}

/** Ladder rung for a tier; free sits below the ladder, enterprise clamps to top. */
export function planRungId(tier: PlanTier): 'brief' | 'desk' | 'studio' | null {
  if (tier === 'free') return null;
  if (tier === 'enterprise') return 'studio';
  return tier;
}

/** "2026-06-23" + "2026-06-23T16:13:04Z" -> "Jun 23, 16:13". Date-only when no timestamp. */
export function formatRunStamp(date: string, createdAt: string | null): string {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const dm = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  const day = dm ? `${months[Number(dm[2]) - 1] ?? dm[2]} ${Number(dm[3])}` : date;
  if (!createdAt) return day;
  const ts = Date.parse(createdAt);
  if (Number.isNaN(ts)) return day;
  const d = new Date(ts);
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${day}, ${hh}:${mm}`;
}
