import type { RunOutcome } from './run-episodes';

/**
 * One vocabulary for "how did this day's run go", shared by the Brief health card and the
 * Pipeline run strip / KPI row so the same day never reads two ways.
 *
 * Health only (accent / warn / mute / idle); never the P&L up/down colours. Carry alone is
 * normal for delta runs (unchanged segments are carried forward) and is NOT a problem.
 */
export type RunStatusKind =
  | 'complete'
  | 'complete-with-carry'
  | 'attention'
  | 'failed'
  | 'unknown'
  | 'no-telemetry'
  | 'no-run';

export type RunStatusTone = 'accent' | 'warn' | 'mute' | 'idle';

export interface RunStatusInput {
  status?: string | null;
  segmentsCarried?: number | null;
  segmentsFailed?: number | null;
  /** Attempts of the episode; >1 with a good final status means it was retried. */
  attempts?: number | null;
  /** Episode outcome from groupRunEpisodes, when the caller has one (retry/recovery is known). */
  outcome?: RunOutcome | null;
}

export interface RunStatusView {
  kind: RunStatusKind;
  tone: RunStatusTone;
  /** Short label (Pipeline surface). */
  label: string;
  /** Full sentence label (Brief card). */
  headline: string;
  /** What the state means, for legends and tooltips. */
  meaning: string;
}

const OK = ['completed', 'complete', 'success', 'succeeded', 'ok'];
const FAIL = ['failed', 'error'];
const PARTIAL = ['partial', 'degraded'];

const VIEWS: Record<Exclude<RunStatusKind, 'unknown'>, Omit<RunStatusView, 'kind'>> = {
  complete: {
    tone: 'accent',
    label: 'Complete',
    headline: 'Pipeline complete',
    meaning: 'Every segment produced fresh output.',
  },
  'complete-with-carry': {
    tone: 'accent',
    label: 'Complete with carry',
    headline: 'Pipeline completed with carry',
    meaning: 'Finished; unchanged segments were carried forward (normal for delta runs).',
  },
  attention: {
    tone: 'warn',
    label: 'Attention',
    headline: 'Pipeline recovered or degraded',
    meaning: 'Finished only after a retry, or ended degraded without carry. Worth a look.',
  },
  failed: {
    tone: 'warn',
    label: 'Failed',
    headline: 'Pipeline needs attention',
    meaning: 'Segments failed or the run ended in failure.',
  },
  'no-telemetry': {
    tone: 'mute',
    label: 'No telemetry',
    headline: 'Pipeline status unavailable',
    meaning: 'A run was recorded but no run-health telemetry exists for it.',
  },
  'no-run': {
    tone: 'idle',
    label: 'No run',
    headline: 'No run',
    meaning: 'No run recorded that day.',
  },
};

/** Higher is worse; picks the representative episode of a day. */
export const RUN_STATUS_SEVERITY: Record<RunStatusKind, number> = {
  'no-run': 0,
  'no-telemetry': 0,
  unknown: 1,
  complete: 1,
  'complete-with-carry': 2,
  attention: 3,
  failed: 4,
};

export function classifyRunStatus(input: RunStatusInput): RunStatusKind {
  const status = (input.status ?? '').toLowerCase();
  const failed = input.segmentsFailed ?? 0;
  const carried = input.segmentsCarried ?? 0;

  if (failed > 0 || input.outcome === 'failed' || FAIL.includes(status)) return 'failed';
  if (input.outcome === 'recovered' || (input.attempts ?? 0) > 1) return 'attention';
  if (PARTIAL.includes(status) || input.outcome === 'degraded' || status.includes('carr')) {
    // Carry evidence with no failure is the normal delta-run shape; without it the run really is degraded.
    return carried > 0 || status.includes('carr') ? 'complete-with-carry' : 'attention';
  }
  if (carried > 0) return 'complete-with-carry';
  if (OK.includes(status) || input.outcome === 'ok') return 'complete';
  return 'unknown';
}

export function runStatusView(kind: RunStatusKind, status?: string | null): RunStatusView {
  if (kind === 'unknown') {
    const s = (status ?? '').trim();
    return {
      kind,
      tone: 'mute',
      label: s || 'Unknown',
      headline: s ? `Pipeline ${s}` : 'Pipeline status unavailable',
      meaning: 'Status not recognised.',
    };
  }
  return { kind, ...VIEWS[kind] };
}

export function describeRunStatus(input: RunStatusInput): RunStatusView {
  return runStatusView(classifyRunStatus(input), input.status);
}
