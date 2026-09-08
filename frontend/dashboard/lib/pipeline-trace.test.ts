import { describe, expect, it } from 'vitest';
import { classifyPipelineTrace } from './pipeline-trace';
import type { PipelineRunEvent } from './pipeline-trace';

const EVENT: PipelineRunEvent = {
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
};

describe('classifyPipelineTrace', () => {
  it('distinguishes a recorded trace from historical absence and query failure', () => {
    expect(classifyPipelineTrace([EVENT], true)).toEqual({
      state: 'available',
      events: [EVENT],
    });
    expect(classifyPipelineTrace([], true)).toEqual({ state: 'not-recorded', events: [] });
    expect(classifyPipelineTrace([], false)).toEqual({ state: 'unavailable', events: [] });
  });
});