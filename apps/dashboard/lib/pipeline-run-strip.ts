import type { RunEpisode, RunOutcome } from './run-episodes';

export type RunStripTone = 'ok' | 'warn' | 'off' | 'idle';

export interface RunStripCell {
  key: string;
  date: string;
  tone: RunStripTone;
  /** Tooltip + accessible name. */
  label: string;
  /** null = no run recorded that day. */
  outcome: RunOutcome | 'no-telemetry' | null;
  attempts: number;
}

export const RUN_STRIP_DAYS = 30;

/** Health tones only (accent/warn/mute); never up/down. */
const OUTCOME_TONE: Record<RunOutcome, RunStripTone> = {
  ok: 'ok',
  recovered: 'warn',
  degraded: 'warn',
  failed: 'warn',
};

const SEVERITY: Record<RunOutcome, number> = { ok: 0, recovered: 1, degraded: 2, failed: 3 };

export function addDays(iso: string, delta: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

/** Worst episode outcome for one date (a date can hold a baseline and a delta run). */
export function worstEpisode(episodes: readonly RunEpisode[]): RunEpisode | null {
  let worst: RunEpisode | null = null;
  for (const e of episodes) {
    if (!worst || SEVERITY[e.outcome] > SEVERITY[worst.outcome]) worst = e;
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
      cells.push({
        key: date,
        date,
        tone: OUTCOME_TONE[worst.outcome],
        outcome: worst.outcome,
        attempts,
        label: `${date}: ${worst.outcome}${attempts > 1 ? `, ${attempts} attempts` : ''}`,
      });
    } else if (runSet.has(date)) {
      cells.push({ key: date, date, tone: 'off', outcome: 'no-telemetry', attempts: 0, label: `${date}: run recorded, no telemetry` });
    } else {
      cells.push({ key: date, date, tone: 'idle', outcome: null, attempts: 0, label: `${date}: no run` });
    }
  }
  return cells;
}

/** Count of run days by health, for the strip legend. */
export function summariseRunStrip(cells: readonly RunStripCell[]): { runs: number; healthy: number; attention: number } {
  let runs = 0;
  let healthy = 0;
  let attention = 0;
  for (const c of cells) {
    if (c.outcome === null) continue;
    runs++;
    if (c.outcome === 'ok') healthy++;
    else if (c.outcome !== 'no-telemetry') attention++;
  }
  return { runs, healthy, attention };
}
