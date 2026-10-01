import { parsePhaseHealth, type PhaseHealth } from './run-phase-health';
import { addDays, episodeKind, RUN_STRIP_DAYS, worstEpisode } from './pipeline-run-strip';
import type { RunStatusKind } from './run-status';
import type { RunEpisode } from './run-episodes';

/** Minimum prior run days before a delta-vs-median is shown. */
export const MIN_DELTA_BASELINE_DAYS = 5;

export interface PipelineDayKpis {
  /** False when no run_health episode exists for the date (cells render as em dashes). */
  hasTelemetry: boolean;
  status: string | null;
  /** Shared status vocabulary (lib/run-status); same reading as the Brief. */
  kind: RunStatusKind;
  /** The run_type the duration delta was compared within (null when none / unknown). */
  runType: string | null;
  durationS: number | null;
  /** Percent change vs the median of prior runs of the SAME run_type; null under MIN_DELTA_BASELINE_DAYS. */
  durationDeltaPct: number | null;
  /** Trailing per-day duration, oldest first; null = no telemetry (gap, not zero). */
  durationSeries: Array<number | null>;
  segments: { ok: number | null; carried: number | null; failed: number | null; total: number | null };
  /** 0 attempts = unknown and is reported as null, never 1. */
  attempts: number | null;
  artifacts: number;
  phases: PhaseHealth[];
}

export function median(values: readonly number[]): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function num(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

export function buildDayKpis(input: {
  date: string;
  episodes: readonly RunEpisode[];
  artifactCount: number;
  days?: number;
}): PipelineDayKpis {
  const days = input.days ?? RUN_STRIP_DAYS;
  const byDate = new Map<string, RunEpisode[]>();
  for (const e of input.episodes) {
    if (!e.runDate) continue;
    const arr = byDate.get(e.runDate) ?? [];
    arr.push(e);
    byDate.set(e.runDate, arr);
  }

  const durationSeries: Array<number | null> = [];
  const today = worstEpisode(byDate.get(input.date) ?? []);
  // A delta run is not comparable to a full run: only same-run_type priors count.
  const prior: number[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = addDays(input.date, -i);
    const worst = worstEpisode(byDate.get(d) ?? []);
    const dur = num(worst?.latest.duration_s);
    durationSeries.push(dur);
    if (i > 0 && today) {
      const sameType = (byDate.get(d) ?? []).find((e) => e.runType === today.runType && num(e.latest.duration_s) != null);
      const sameDur = num(sameType?.latest.duration_s);
      if (sameDur != null) prior.push(sameDur);
    }
  }

  if (!today) {
    return {
      hasTelemetry: false,
      status: null,
      kind: 'no-telemetry',
      runType: null,
      durationS: null,
      durationDeltaPct: null,
      durationSeries,
      segments: { ok: null, carried: null, failed: null, total: null },
      attempts: null,
      artifacts: input.artifactCount,
      phases: [],
    };
  }

  const durationS = num(today.latest.duration_s);
  const base = prior.length >= MIN_DELTA_BASELINE_DAYS ? median(prior) : null;
  const durationDeltaPct =
    durationS != null && base != null && base > 0 ? ((durationS - base) / base) * 100 : null;

  return {
    hasTelemetry: true,
    status: today.latest.status ?? null,
    kind: episodeKind(today),
    runType: today.runType,
    durationS,
    durationDeltaPct,
    durationSeries,
    segments: {
      ok: num(today.latest.segments_ok),
      carried: num(today.latest.segments_carried),
      failed: num(today.latest.segments_failed),
      total: num(today.latest.segments_total),
    },
    attempts: today.attempts > 0 ? today.attempts : null,
    artifacts: input.artifactCount,
    phases: parsePhaseHealth(today.latest.breakdown ?? null),
  };
}

export function formatDeltaPct(pct: number | null): string | null {
  if (pct == null || !Number.isFinite(pct)) return null;
  const r = Math.round(pct);
  return `${r > 0 ? '+' : ''}${r}% vs median`;
}
