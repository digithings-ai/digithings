import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PipelineTraceLedger, {
  PipelineTraceView,
  filterPipelineTraceEvents,
  groupPipelineTraceEvents,
} from './PipelineTraceLedger';
import type { PipelineRunEvent } from '@/lib/pipeline-trace';

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

describe('PipelineTraceLedger', () => {
  it('groups calls by run attempt and phase while preserving order', () => {
    const groups = groupPipelineTraceEvents([
      event(),
      event({ sequence: 2, phase: 'phase2', operation: 'RatesReport' }),
      event({ sequence: 1, attempt: 2, phase: 'phase1' }),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups[0].phases.map((phase) => phase.label)).toEqual(['phase1', 'phase2']);
    expect(groups[0].phases[0].events[0].sequence).toBe(1);
    expect(groups[1].attempt).toBe(2);
  });

  it('searches labels and isolates retries and errors', () => {
    const events = [
      event(),
      event({ sequence: 2, event_kind: 'tool_call', name: 'get_macro_series' }),
      event({ sequence: 3, status: 'error', operation: 'SectorReport' }),
      event({ sequence: 4, retry_count: 2, operation: 'RatesReport' }),
    ];

    expect(filterPipelineTraceEvents(events, 'macro_series', 'all', 'all')).toHaveLength(1);
    expect(filterPipelineTraceEvents(events, '', 'tool_call', 'all')).toHaveLength(1);
    expect(filterPipelineTraceEvents(events, '', 'all', 'issues').map((item) => item.sequence))
      .toEqual([3, 4]);
    expect(
      filterPipelineTraceEvents(events, '', 'all', 'all', 'research').map((item) => item.sequence),
    ).toEqual([1, 2, 3, 4]);
    expect(filterPipelineTraceEvents(events, '', 'all', 'all', 'inputs')).toHaveLength(0);
  });

  it('renders a typed gap when Inputs has no call telemetry', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineTraceView, {
        result: {
          state: 'available',
          events: [event({ document_key: 'macro', phase: 'phase1' })],
        },
        date: '2026-08-05',
        onClose: () => {},
      }),
    );

    expect(html).toContain('Pipeline stage filter');
    expect(html).toContain('All stages');
    expect(html).toContain('Research');
  });

  it('pages a 300-call result set with load-more remaining counts', () => {
    const events = Array.from({ length: 300 }, (_, index) =>
      event({
        sequence: index + 1,
        document_key: index % 2 === 0 ? 'macro' : 'analyst/QQQ',
        phase: index % 2 === 0 ? 'phase1' : 'h5_analyst-QQQ',
        operation: `Op${index + 1}`,
      }),
    );
    const html = renderToStaticMarkup(
      createElement(PipelineTraceView, {
        result: { state: 'available', events },
        date: '2026-08-05',
        onClose: () => {},
      }),
    );

    expect(html).toContain('300 calls');
    expect(html).toContain('Load 100 more · 200 remaining');
    expect((html.match(/data-testid="pipeline-trace-event"/g) ?? []).length).toBe(100);
  });

  it('renders failures and retries expanded but routine calls collapsed', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineTraceView, {
        result: {
          state: 'available',
          events: [
            event(),
            event({ sequence: 2, status: 'error', operation: 'SectorReport' }),
            event({ sequence: 3, retry_count: 1, operation: 'RatesReport' }),
          ],
        },
        date: '2026-08-05',
        onClose: () => {},
      }),
    );

    expect(html).toContain('3 calls');
    expect(html).toContain('1 retries');
    expect(html).toContain('1 errors');
    const detailTags = html.match(/<details[^>]*>/g) ?? [];
    expect(detailTags).toHaveLength(3);
    expect(detailTags.filter((tag) => tag.includes(' open=""'))).toHaveLength(2);
    expect(detailTags[0]).not.toContain(' open=""');
  });

  it('renders distinct historical and unavailable states', () => {
    const historical = renderToStaticMarkup(
      createElement(PipelineTraceView, {
        result: { state: 'not-recorded', events: [] },
        date: '2026-07-01',
        onClose: () => {},
      }),
    );
    const unavailable = renderToStaticMarkup(
      createElement(PipelineTraceView, {
        result: { state: 'unavailable', events: [] },
        date: '2026-08-05',
        onClose: () => {},
      }),
    );

    expect(historical).toContain('Call details were not recorded for this run.');
    expect(unavailable).toContain('Call trace could not be loaded for 2026-08-05.');
  });

  it('uses a full mobile overlay and wide desktop reader while loading', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineTraceLedger, { date: '2026-08-05', onClose: () => {} }),
    );

    expect(html).toContain('fixed inset-0');
    expect(html).toContain('h-dvh');
    expect(html).toContain('md:relative');
    expect(html).toContain('md:w-[min(78vw,1040px)]');
  });
});
