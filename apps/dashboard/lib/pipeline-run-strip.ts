import type { RunEpisode } from './run-episodes';
import { classifyRunStatus, RUN_STATUS_SEVERITY, runStatusView, type RunStatusKind } from './run-status';

export type RunStripTone = 'ok' | 'warn' | 'off' | 'idle';

export interface RunStripCell {
  key: string;
  date: string;
  tone: RunStripTone;
  /** Tooltip + accessible name. */
  label: string;
  /** Shared vocabulary (lib/run-status), identical to the Brief's reading of the same day. */
  kind: RunStatusKind;
  /** null = no run recorded that day. */
  outcome: RunEpisode['outcome'] | 'no-telemetry' | null;
  attempts: number;
}

export const RUN_STRIP_DAYS = 30;

/** Health tones only (accent/warn/mute); never up/down. Carry is accent: normal for delta runs. */
const TONE: Record<ReturnType<typeof runStatusView>['tone'], RunStripTone> = {
  accent: 'ok',
  warn: 'warn',
  mute: 'off',
  idle: 'idle',
};

/** Shared classification of one episode (status, carry, failures, retries). */
export function episodeKind(e: RunEpisode): RunStatusKind {
  return classifyRunStatus({
    status: e.latest.status,
    segmentsCarried: e.latest.segments_carried,
    segmentsFailed: e.latest.segments_failed,
    attempts: e.attempts,
    outcome: e.outcome,
  });
}

export function addDays(iso: string, delta: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

/** Worst episode outcome for one date (a date can hold a baseline and a delta run). */
export function worstEpisode(episodes: readonly RunEpisode[]): RunEpisode | null {
  let worst: RunEpisode | null = null;
  for (const e of episodes) {
    if (!worst || RUN_STATUS_SEVERITY[episodeKind(e)] > RUN_STATUS_SEVERITY[episodeKind(worst)]) worst = e;
  }
  return worst;
}

/**
 * The trailing `days` calendar days ending at `end`, oldest first. A day is a run
 * day when it is in `runDates` (daily_snapshots); its tone comes from run_health
 * episodes when present, else `off` (run recorded, no telemetry).
 */
export function buildRunStrip(input: {
  runDates: readonly string[];
  episodes: readonly RunEpisode[];
  end: string;
  days?: number;
}): RunStripCell[] {
  const days = input.days ?? RUN_STRIP_DAYS;
  const runSet = new Set(input.runDates);
  const byDate = new Map<string, RunEpisode[]>();
  for (const e of input.episodes) {
    if (!e.runDate) continue;
    const arr = byDate.get(e.runDate) ?? [];
    arr.push(e);
    byDate.set(e.runDate, arr);
  }
  const cells: RunStripCell[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const date = addDays(input.end, -i);
    const worst = worstEpisode(byDate.get(date) ?? []);
    if (worst) {
      const attempts = worst.attempts;
      const view = runStatusView(episodeKind(worst), worst.latest.status);
      cells.push({
        key: date,
        date,
        tone: TONE[view.tone],
        kind: view.kind,
        outcome: worst.outcome,
        attempts,
        label: `${date}: ${view.label.toLowerCase()}${attempts > 1 ? `, ${attempts} attempts` : ''}`,
      });
    } else if (runSet.has(date)) {
      cells.push({ key: date, date, tone: 'off', kind: 'no-telemetry', outcome: 'no-telemetry', attempts: 0, label: `${date}: run recorded, no telemetry` });
    } else {
      cells.push({ key: date, date, tone: 'idle', kind: 'no-run', outcome: null, attempts: 0, label: `${date}: no run` });
    }
  }
  return cells;
}

/** Count of run days by health, for the strip legend. Carry is healthy; only retried/degraded/failed need attention. */
export function summariseRunStrip(cells: readonly RunStripCell[]): {
  runs: number;
  healthy: number;
  attention: number;
  carried: number;
} {
  let runs = 0;
  let healthy = 0;
  let attention = 0;
  let carried = 0;
  for (const c of cells) {
    if (c.kind === 'no-run') continue;
    runs++;
    if (c.kind === 'complete') healthy++;
    else if (c.kind === 'complete-with-carry') carried++;
    else if (c.kind === 'attention' || c.kind === 'failed') attention++;
  }
  return { runs, healthy, attention, carried };
}
