import type { PipelineDayData } from './pipeline-graph-data';

/**
 * LOCKED deep-link grammar for the Pipeline hub (Surface 1).
 * `/pipeline?date=YYYY-MM-DD&stage=<stage>&node=<document_key>`
 * "open day D, expand stage S, focus node N." Keyed off `document_key`, NOT the
 * legacy `path` field. Six consumers depend on this exact shape; do not drift.
 */
export type PipelineStage = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';

/**
 * The digest is published under different `document_key`s depending on
 * `run_type` (`publish_phase.py`): baseline runs (the Sunday `refresh_scope=all`
 * cron) write `digest`; every other day (the `delta` cadence — the majority of
 * days) writes `digest-delta`. Callers that don't know today's cadence (Overview
 * "See the full read" links, the command palette) should treat `'digest'` as a
 * generic sentinel and resolve it against a day's real `presentKeys` via
 * `resolvePresentDigestKey`, not assume it is the literal key on every day.
 */
export const DIGEST_DOCUMENT_KEYS = ['digest', 'digest-delta'] as const;

/** Whichever digest key is actually present for a given day, if any. */
export function resolvePresentDigestKey(day: PipelineDayData): string | undefined {
  return DIGEST_DOCUMENT_KEYS.find((k) => day.presentKeys.has(k));
}

export function buildPipelineHref(opts: {
  date?: string | null;
  stage?: PipelineStage | null;
  node?: string | null;
}): string {
  const p = new URLSearchParams();
  if (opts.date) p.set('date', opts.date);
  if (opts.stage) p.set('stage', opts.stage);
  if (opts.node) p.set('node', opts.node);
  const qs = p.toString();
  return qs ? `/pipeline?${qs}` : '/pipeline';
}

const PIPELINE_STAGES: readonly PipelineStage[] = ['inputs', 'research', 'synthesis', 'selection', 'decision'];

/** Parse URLSearchParams into typed pipeline navigation params. Unknown stage values are omitted. */
export function parsePipelineParams(sp: URLSearchParams): { date?: string; stage?: PipelineStage; node?: string } {
  const result: { date?: string; stage?: PipelineStage; node?: string } = {};
  const date = sp.get('date');
  if (date) result.date = date;
  const stage = sp.get('stage');
  if (stage && (PIPELINE_STAGES as readonly string[]).includes(stage)) result.stage = stage as PipelineStage;
  const node = sp.get('node');
  if (node) result.node = node;
  return result;
}

/** Map a sub-step id (+ optional branch qualifier) to its document_key. Returns null for unknown sub-steps. */
export function leafDocumentKey(subStepId: string, branch?: string): string | null {
  switch (subStepId) {
    case 'macro': return 'macro';
    case 'consolidate': return 'sector-scorecard';
    case 'digest': return 'digest';
    case 'pm-direction': return 'pm-direction-memo';
    case 'risk-sizing': return 'pm-rebalance';
    case 'analysts': return branch ? `analyst/${branch}` : null;
    case 'deliberation': return branch ? `deliberation/${branch}` : null;
    case 'commit': return branch ? `commit-run/${branch}` : null;
    default: return null;
  }
}

/** Map a `document_key` to the stage that owns it (per the spec topology table). */
export function stageForDocumentKey(documentKey: string): PipelineStage | null {
  const k = documentKey.toLowerCase();
  if ((DIGEST_DOCUMENT_KEYS as readonly string[]).includes(k)) return 'synthesis';
  if (k.startsWith('analyst/') || k.startsWith('deliberation/')) return 'selection';
  if (k === 'pm-direction-memo' || k === 'pm-rebalance' || k === 'risk-debate') return 'selection';
  if (k.startsWith('commit-run/')) return 'decision';
  if (
    k.startsWith('alt-') ||
    k.startsWith('inst-') ||
    k.startsWith('sector-') ||
    k === 'macro' ||
    ['bonds', 'commodities', 'forex', 'crypto', 'equity', 'international'].includes(k)
  ) {
    return 'research';
  }
  if (k === 'preflight' || k.startsWith('market-data')) return 'inputs';
  return null;
}
