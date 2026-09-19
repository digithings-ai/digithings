import { describe, expect, it } from 'vitest';
import type { PipelineRunEvent } from './pipeline-trace';
import {
  TRACE_SCALE_TARGET,
  TRACE_STAGE_COVERAGE,
  TRACE_UI_PAGE_SIZE,
  classifyTraceStageEmpty,
  filterPipelineTraceByStage,
  nextTracePageLimit,
  paginatePipelineTraceEvents,
  stageForTraceEvent,
  stageForTracePhase,
} from './pipeline-trace-stage';

function event(overrides: Partial<PipelineRunEvent> = {}): PipelineRunEvent {
  return {
    run_id: 'run-2026-08-05',
    attempt: 1,
    run_date: '2026-08-05',
    run_type: 'delta',
    sequence: 1,
    event_kind: 'model_call',
    phase: 'phase1',
    operation: 'MacroReport',
    document_key: 'macro',
    name: 'openrouter/auto',
    status: 'ok',
    duration_ms: 125,
    retry_count: 0,
    sources: 0,
    input_summary: 'Structured model request',
    output_summary: '40 completion tokens',
    created_at: '2026-08-05T12:00:00Z',
    ...overrides,
  };
}

function buildScaleFixture(count: number): PipelineRunEvent[] {
  return Array.from({ length: count }, (_, index) => {
    const sequence = index + 1;
    const band = sequence % 5;
    if (band === 0) {
      return event({
        sequence,
        phase: 'h5_analyst-QQQ',
        operation: 'AssetAnalyst',
        document_key: 'analyst/QQQ',
        event_kind: sequence % 2 === 0 ? 'tool_call' : 'model_call',
        name: sequence % 2 === 0 ? 'get_prices' : 'openrouter/auto',
      });
    }
    if (band === 1) {
      return event({
        sequence,
        phase: 'publish-digest',
        operation: 'Digest',
        document_key: sequence % 2 === 0 ? 'digest-delta' : 'digest',
      });
    }
    if (band === 2) {
      return event({
        sequence,
        phase: 'beliefs-distillation',
        operation: 'Beliefs',
        document_key: 'beliefs',
      });
    }
    if (band === 3) {
      return event({
        sequence,
        phase: 'portfolio_h9_commit_run',
        operation: 'Commit',
        document_key: `commit-run/${1000 + sequence}`,
      });
    }
    return event({
      sequence,
      phase: `phase${(sequence % 4) + 1}`,
      operation: 'SectorReport',
      document_key: `sector-technology`,
      status: sequence % 47 === 0 ? 'error' : 'ok',
      retry_count: sequence % 53 === 0 ? 1 : 0,
    });
  });
}

describe('pipeline-trace-stage', () => {
  it('maps document_key and phase slugs onto topology stages', () => {
    expect(stageForTraceEvent(event())).toBe('research');
    expect(stageForTraceEvent(event({ document_key: 'analyst/IJR', phase: null }))).toBe(
      'selection',
    );
    expect(stageForTraceEvent(event({ document_key: null, phase: 'h6_pm_challenge-EWT' }))).toBe(
      'selection',
    );
    expect(stageForTracePhase('beliefs-distillation')).toBe('learning');
    expect(stageForTracePhase('preflight-market-data')).toBe('inputs');
  });

  it('documents Inputs as a typed call-persistence gap and other bands as emitters', () => {
    expect(TRACE_STAGE_COVERAGE.inputs).toBe('typed-gap');
    expect(TRACE_STAGE_COVERAGE.research).toBe('emits-calls');
    expect(TRACE_STAGE_COVERAGE.selection).toBe('emits-calls');
    expect(classifyTraceStageEmpty('inputs', 120)).toBe('typed-gap');
    expect(classifyTraceStageEmpty('research', 120)).toBe('filter-miss');
    expect(classifyTraceStageEmpty('all', 120)).toBe('none');
  });

  it('filters and paginates a ~300-call fixture without dropping order', () => {
    const events = buildScaleFixture(TRACE_SCALE_TARGET);
    expect(events).toHaveLength(TRACE_SCALE_TARGET);

    const research = filterPipelineTraceByStage(events, 'research');
    const selection = filterPipelineTraceByStage(events, 'selection');
    expect(research.length + selection.length).toBeGreaterThan(0);
    expect(research.every((row) => stageForTraceEvent(row) === 'research')).toBe(true);

    let limit = TRACE_UI_PAGE_SIZE;
    const first = paginatePipelineTraceEvents(events, limit);
    expect(first).toHaveLength(TRACE_UI_PAGE_SIZE);
    expect(first[0].sequence).toBe(1);
    expect(first[TRACE_UI_PAGE_SIZE - 1].sequence).toBe(TRACE_UI_PAGE_SIZE);

    limit = nextTracePageLimit(limit, events.length);
    expect(limit).toBe(200);
    limit = nextTracePageLimit(limit, events.length);
    expect(limit).toBe(TRACE_SCALE_TARGET);

    const allVisible = paginatePipelineTraceEvents(events, limit);
    expect(allVisible).toHaveLength(TRACE_SCALE_TARGET);
    expect(allVisible.map((row) => row.sequence)).toEqual(
      Array.from({ length: TRACE_SCALE_TARGET }, (_, i) => i + 1),
    );
  });
});
