import type { PipelineStage } from './pipeline-links';
import { stageForDocumentKey } from './pipeline-links';
import type { PipelineRunEvent } from './pipeline-trace';
import { PIPELINE_TOPOLOGY } from './pipeline-topology';

/** UI page size for Call trace load-more (README + #1945 ~300-call scale). */
export const TRACE_UI_PAGE_SIZE = 100;

/** Acceptance target for searchable/paginated detail (#1945 / #2622). */
export const TRACE_SCALE_TARGET = 300;

export type TraceStageFilter = 'all' | PipelineStage;

/**
 * How call-level telemetry relates to a topology stage.
 * - `emits-calls` — digigraph usage can record model/search/tool rows for this band
 * - `typed-gap` — stage is state-only / non-LLM; UI must not invent call rows
 */
export type TraceStageCoverage = 'emits-calls' | 'typed-gap';

const PIPELINE_STAGES: readonly PipelineStage[] = [
  'inputs',
  'research',
  'synthesis',
  'selection',
  'decision',
  'learning',
];

/**
 * Stage-level call persistence contract for glass-box honesty.
 * Sub-steps that are state-only still sit under a stage that *can* emit when
 * sibling LLM nodes run; only Inputs is entirely non-LLM today (preflight +
 * attention-plan publish without model/tool call capture on that band).
 */
export const TRACE_STAGE_COVERAGE: Record<PipelineStage, TraceStageCoverage> = {
  inputs: 'typed-gap',
  research: 'emits-calls',
  synthesis: 'emits-calls',
  selection: 'emits-calls',
  decision: 'emits-calls',
  learning: 'emits-calls',
};

/** Human labels for stage filter chrome (match PIPELINE_TOPOLOGY). */
export function traceStageLabel(stage: PipelineStage): string {
  return PIPELINE_TOPOLOGY.find((item) => item.id === stage)?.label ?? stage;
}

/**
 * Map a persisted call row onto a topology stage.
 * Prefer `document_key` (same grammar as Pipeline deep links); fall back to
 * phase slug heuristics when the writer left document_key null.
 */
export function stageForTraceEvent(event: PipelineRunEvent): PipelineStage | null {
  if (event.document_key) {
    const fromKey = stageForDocumentKey(event.document_key);
    if (fromKey) return fromKey;
  }
  return stageForTracePhase(event.phase);
}

export function stageForTracePhase(phase: string | null): PipelineStage | null {
  if (!phase) return null;
  const p = phase.toLowerCase();
  if (p.includes('belief')) return 'learning';
  if (p.includes('commit')) return 'decision';
  if (
    p.includes('digest') ||
    p.includes('consolidat') ||
    p.includes('phase6') ||
    p.includes('master')
  ) {
    return 'synthesis';
  }
  if (
    p.startsWith('h1') ||
    p.startsWith('h2') ||
    p.startsWith('h3') ||
    p.startsWith('h4') ||
    p.startsWith('h5') ||
    p.startsWith('h6') ||
    p.startsWith('h7') ||
    p.includes('phase7') ||
    p.includes('thesis') ||
    p.includes('screener') ||
    p.includes('analyst') ||
    p.includes('deliberat') ||
    p.includes('pm-') ||
    p.includes('pm_') ||
    p.includes('risk') ||
    p.includes('rebalance') ||
    p.includes('sizing')
  ) {
    return 'selection';
  }
  if (
    p.includes('preflight') ||
    p.includes('attention') ||
    p.includes('market-data') ||
    p.includes('market_data')
  ) {
    return 'inputs';
  }
  if (
    p.includes('macro') ||
    p.includes('sector') ||
    p.includes('alt-') ||
    p.includes('alt_') ||
    p.includes('inst-') ||
    p.includes('inst_') ||
    p.includes('asset') ||
    p.includes('scorecard') ||
    p.includes('research') ||
    p.includes('phase1') ||
    p.includes('phase2') ||
    p.includes('phase3') ||
    p.includes('phase4') ||
    p.includes('phase5')
  ) {
    return 'research';
  }
  return null;
}

export function filterPipelineTraceByStage(
  events: PipelineRunEvent[],
  stage: TraceStageFilter,
): PipelineRunEvent[] {
  if (stage === 'all') return events;
  return events.filter((event) => stageForTraceEvent(event) === stage);
}

/** First `limit` events in persisted order (already sorted by fetch). */
export function paginatePipelineTraceEvents(
  events: PipelineRunEvent[],
  limit: number,
): PipelineRunEvent[] {
  if (limit <= 0) return [];
  return events.slice(0, limit);
}

export function nextTracePageLimit(currentLimit: number, total: number): number {
  return Math.min(total, currentLimit + TRACE_UI_PAGE_SIZE);
}

export function isPipelineStageFilter(value: string): value is TraceStageFilter {
  return value === 'all' || (PIPELINE_STAGES as readonly string[]).includes(value);
}

export function pipelineStageFilters(): readonly TraceStageFilter[] {
  return ['all', ...PIPELINE_STAGES];
}

/**
 * Empty-state reason when a stage filter yields zero rows among an available trace.
 * Typed-gap stages never invent calls; filter misses are ordinary.
 */
export function classifyTraceStageEmpty(
  stage: TraceStageFilter,
  availableEventCount: number,
): 'none' | 'typed-gap' | 'filter-miss' {
  if (stage === 'all' || availableEventCount === 0) return 'none';
  if (TRACE_STAGE_COVERAGE[stage] === 'typed-gap') return 'typed-gap';
  return 'filter-miss';
}
