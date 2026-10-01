import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/observability-queries', () => ({
  fetchResearchRunDiagnostics: vi.fn(() => Promise.resolve([])),
  fetchResearchRunDiagnosticsResult: vi.fn(() => Promise.resolve({ rows: [], ok: true })),
}));

import PipelineRunStrip from './PipelineRunStrip';
import PipelineKpiStrip, { PipelineKpiDetail } from './PipelineKpiStrip';
import PipelineRunHealth from './PipelineRunHealth';
import PipelineNode from './PipelineNode';
import { PipelineTimelineView } from './PipelineTimeline';
import { buildPipelineTimeline, timelineCallsLabel } from '@/lib/pipeline-timeline';
import { buildRunStrip } from '@/lib/pipeline-run-strip';
import { fanoutCompleteness } from '@/lib/pipeline-graph-data';
import { buildDayKpis } from '@/lib/pipeline-kpis';
import type { PipelineRunEvent } from '@/lib/pipeline-trace';
import { groupRunEpisodes } from '@/lib/run-episodes';
import type { RunEpisode } from '@/lib/run-episodes';
import type { ResearchRunDiagnostics } from '@/lib/types';
import type { LaidOutNode } from '@/lib/pipeline-layout';

function episode(date: string, over: Partial<ResearchRunDiagnostics> = {}): RunEpisode {
  const latest = {
    run_date: date,
    status: 'ok',
    duration_s: 754,
    segments_ok: 12,
    segments_total: 14,
    segments_carried: 1,
    segments_failed: 1,
    breakdown: { phase1_outputs: { ok: 5, failed: 0, carried: 1 } },
    ...over,
  } as ResearchRunDiagnostics;
  return { key: `${date}|b`, runDate: date, runType: 'b', attempts: 2, outcome: 'ok', latest, errorSummary: null };
}

describe('PipelineRunStrip', () => {
  it('renders 30 toned cells, marks the selected date and is actionable only for run days', () => {
    const cells = buildRunStrip({ runDates: ['2026-09-29', '2026-09-30'], episodes: [episode('2026-09-30')], end: '2026-09-30' });
    const html = renderToStaticMarkup(createElement(PipelineRunStrip, { cells, selectedDate: '2026-09-30', onSelect: () => {} }));
    expect(html).toContain('data-testid="pipeline-run-strip"');
    expect((html.match(/data-slot="status-strip-cell"/g) ?? []).length).toBe(30);
    expect(html).toContain('data-tone="ok"');
    expect(html).toContain('data-tone="off"');
    expect(html).toContain('data-tone="idle"');
    expect(html).toContain('pipeline-run-strip-marker');
    expect(html).not.toContain('overflow-x-auto');
    // Real clickability: kit cells are inert (no buttons); only the 2 run days get a button.
    expect(html).not.toMatch(/<button[^>]*data-slot="status-strip-cell"/);
    const buttons = html.match(/data-testid="pipeline-run-strip-select"/g) ?? [];
    expect(buttons.length).toBe(2);
    // Legend says what each colour means, including that carry is normal.
    expect(html).toContain('data-testid="pipeline-run-strip-legend"');
    expect(html).toContain('complete (carry is normal)');
    expect(html).toContain('retried or failed');
    expect(html).toContain('no telemetry');
    expect(html).toContain('aria-label="Open 2026-09-30: failed, 2 attempts"');
    expect(html).toContain('aria-label="Open 2026-09-29: run recorded, no telemetry"');
    expect(html).not.toContain('aria-label="Open 2026-09-28: no run"');
  });

  it('shows a skeleton while loading', () => {
    const html = renderToStaticMarkup(createElement(PipelineRunStrip, { cells: [], selectedDate: 'x', onSelect: () => {}, loading: true }));
    expect(html).toContain('aria-busy="true"');
  });
});

describe('PipelineKpiStrip', () => {
  it('renders one compact inline row of KPI chips with the duration sparkline (no composition bars)', () => {
    const kpis = buildDayKpis({ date: '2026-09-30', episodes: [episode('2026-09-30')], artifactCount: 41 });
    const html = renderToStaticMarkup(createElement(PipelineKpiStrip, { kpis }));
    expect(html).toContain('12m 34s');
    expect(html).toContain('12/14');
    expect(html).toContain('>41<');
    expect(html).toContain('Run duration, last 30 days');
    expect(html).not.toContain('data-slot="composition-bar"');
    expect(html).not.toContain('data-slot="stat"');
  });

  it('shows the duration delta only when it is comparable (same run_type, >= 5 priors)', () => {
    const priors = [1, 2, 3, 4, 5].map((i) => episode(`2026-09-${20 + i}`, { duration_s: 100 }));
    const kpis = buildDayKpis({ date: '2026-09-30', episodes: [...priors, episode('2026-09-30', { duration_s: 150 })], artifactCount: 0 });
    expect(renderToStaticMarkup(createElement(PipelineKpiStrip, { kpis }))).toContain('+50% vs median');
    const delta = { ...episode('2026-09-30', { duration_s: 5 }), runType: 'delta' };
    const hidden = buildDayKpis({ date: '2026-09-30', episodes: [...priors, delta], artifactCount: 0 });
    expect(renderToStaticMarkup(createElement(PipelineKpiStrip, { kpis: hidden }))).not.toContain('vs median');
  });

  it('renders em dashes, never zeros, without telemetry', () => {
    const kpis = buildDayKpis({ date: '2026-09-30', episodes: [], artifactCount: 0 });
    const html = renderToStaticMarkup(createElement(PipelineKpiStrip, { kpis }));
    expect(html).toContain('—');
  });
});

describe('PipelineKpiDetail', () => {
  it('renders the segment composition bar and phase bars', () => {
    const kpis = buildDayKpis({ date: '2026-09-30', episodes: [episode('2026-09-30')], artifactCount: 41 });
    const html = renderToStaticMarkup(createElement(PipelineKpiDetail, { kpis }));
    expect(html).toContain('data-slot="composition-bar"');
    expect(html).toContain('data-testid="pipeline-phase-health"');
    expect(html).toContain('Segments: 12 ok, 1 carried, 1 failed of 14');
  });

  it('draws no composition bar without telemetry', () => {
    const kpis = buildDayKpis({ date: '2026-09-30', episodes: [], artifactCount: 0 });
    expect(renderToStaticMarkup(createElement(PipelineKpiDetail, { kpis }))).not.toContain('data-slot="composition-bar"');
  });
});

describe('PipelineRunHealth', () => {
  it('renders from a parent-owned state (no self-fetch) with its loading skeleton', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', state: { diagnostics: null, loading: true } }),
    );
    expect(html).toContain('data-testid="pipeline-run-health"');
    expect(html).toContain('Loading…');
  });

  it('says run data is unavailable (not "No run telemetry") when the fetch failed', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', state: { diagnostics: [], loading: false, unavailable: true } }),
    );
    expect(html).toContain('Run data unavailable');
    expect(html).not.toContain('No run telemetry');
    expect(html).not.toContain('No run for this date');
  });

  it('keeps "No run telemetry" for a successful empty read', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', state: { diagnostics: [], loading: false } }),
    );
    expect(html).toContain('No run telemetry');
    expect(html).not.toContain('Run data unavailable');
  });

  it('header status comes from the worst episode, same source as the KPIs', () => {
    const bad = episode('2026-09-30', { status: 'failed', run_type: 'delta' });
    const good = episode('2026-09-30', { status: 'ok', segments_failed: 0, segments_carried: 0 });
    // The ok row is first; a dayRuns[0] header would say "ok".
    const diagnostics = [good.latest, bad.latest];
    const html = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', state: { diagnostics, loading: false } }),
    );
    const kpis = buildDayKpis({ date: '2026-09-30', episodes: groupRunEpisodes(diagnostics), artifactCount: 0 });
    expect(kpis.status).toBe('failed');
    expect(html).toContain('data-status-kind="failed"');
    expect(html).toContain('>Failed<');
  });

  it('is collapsed by default: KPI row visible, detail (phase bars, composition) not rendered', () => {
    const d = episode('2026-09-30', { run_type: 'b', created_at: '2026-09-30T06:00:00Z' }).latest;
    const html = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', tier: 'desk', state: { diagnostics: [d], loading: false } }),
    );
    expect(html).toContain('data-testid="pipeline-kpi-strip"');
    expect(html).not.toContain('data-testid="pipeline-phase-health"');
    expect(html).not.toContain('data-slot="composition-bar"');
  });

  it('reads a carry-only day as complete-with-carry (accent), matching the Brief', () => {
    const d = episode('2026-09-30', { status: 'degraded', segments_failed: 0, segments_carried: 4, run_type: 'delta' }).latest;
    const html = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', tier: 'desk', state: { diagnostics: [d], loading: false } }),
    );
    expect(html).toContain('data-status-kind="complete-with-carry"');
    expect(html).toContain('Complete with carry');
    expect(html).not.toContain('degraded');
  });

  it('gates the economics chips below Desk but keeps status and freshness visible', () => {
    const d = episode('2026-09-30', { status: 'ok', segments_failed: 0, segments_carried: 0, run_type: 'b' }).latest;
    const html = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', tier: 'free', state: { diagnostics: [d], loading: false } }),
    );
    expect(html).not.toContain('data-testid="pipeline-kpi-strip"');
    expect(html).toContain('data-status-kind="complete"');
    expect(html).toContain('data-testid="pipeline-freshness"');
  });

  it('folds freshness into the row and warns when the day has no successful run', () => {
    const ok = episode('2026-09-30', { status: 'ok', segments_failed: 0, run_type: 'b', created_at: '2026-09-30T06:00:00Z' }).latest;
    const okHtml = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', tier: 'desk', state: { diagnostics: [ok], loading: false } }),
    );
    expect(okHtml).toContain('data-testid="pipeline-freshness"');
    expect(okHtml).toContain('Last successful run');
    const bad = episode('2026-09-30', { status: 'failed' }).latest;
    const badHtml = renderToStaticMarkup(
      createElement(PipelineRunHealth, { date: '2026-09-30', tier: 'desk', state: { diagnostics: [bad], loading: false } }),
    );
    expect(badHtml).toContain('No successful run on 2026-09-30');
  });
});

describe('PipelineNode fan-out completeness', () => {
  const node = { id: 'research:alt-data', kind: 'substep', stageId: 'research', label: 'alt-data', x: 0, y: 0, width: 160, height: 48 } as LaidOutNode;
  it('draws a completeness bar when count and total are known', () => {
    const html = renderToStaticMarkup(createElement(PipelineNode, { node, count: 4, completeness: { present: 4, total: 6, complete: false }, expandable: true, onActivate: () => {} }));
    expect(html).toContain('pipeline-node-completeness');
    expect(html).toContain('4 of 6 branches');
    expect(html).toContain('bg-warn');
  });
  it('draws no bar without completeness', () => {
    const html = renderToStaticMarkup(createElement(PipelineNode, { node, count: 6, expandable: true, onActivate: () => {} }));
    expect(html).not.toContain('pipeline-node-completeness');
  });
  it('derives completeness through the real day-data path', () => {
    const fo = { id: 'alt-data', defaultCount: 6 };
    const render = (c: ReturnType<typeof fanoutCompleteness>) =>
      renderToStaticMarkup(createElement(PipelineNode, { node, count: c?.present, completeness: c, expandable: true, onActivate: () => {} }));
    // no run / loading / API down: no bar even though the topology default is 6
    expect(fanoutCompleteness({ runRecorded: false, fanoutCounts: {} }, fo)).toBeUndefined();
    expect(fanoutCompleteness({ fanoutCounts: {} }, fo)).toBeUndefined();
    expect(render(fanoutCompleteness({ runRecorded: false, fanoutCounts: {} }, fo))).not.toContain('pipeline-node-completeness');
    // recorded run, fan-out absent (day-data omits zero counts): empty warn bar
    const zero = render(fanoutCompleteness({ runRecorded: true, fanoutCounts: {} }, fo));
    expect(zero).toContain('0 of 6 branches');
    expect(zero).toContain('bg-warn');
    expect(zero).toContain('width:0%');
    // exactly complete
    const full = render(fanoutCompleteness({ runRecorded: true, fanoutCounts: { 'alt-data': 6 } }, fo));
    expect(full).toContain('bg-accent');
    // surplus must not read as complete
    const over = fanoutCompleteness({ runRecorded: true, fanoutCounts: { 'alt-data': 8 } }, fo);
    expect(over?.complete).toBe(false);
    const overHtml = render(over);
    expect(overHtml).toContain('more than expected');
    expect(overHtml).toContain('bg-warn');
    expect(overHtml).not.toContain('block h-full bg-accent');
  });
  it('omits the bar without completeness (legacy)', () => {
    const html = renderToStaticMarkup(createElement(PipelineNode, { node, count: 4, expandable: true, onActivate: () => {} }));
    expect(html).not.toContain('pipeline-node-completeness');
  });
});

describe('PipelineTimelineView', () => {
  const event = { run_id: 'r', attempt: 1, sequence: 1, event_kind: 'model_call', phase: 'research', document_key: 'macro', name: null, status: 'ok', duration_ms: 2000, retry_count: 0, created_at: null } as unknown as PipelineRunEvent;

  it('draws the waterfall for an available trace', () => {
    const html = renderToStaticMarkup(createElement(PipelineTimelineView, { result: { state: 'available', events: [event] } }));
    expect(html).toContain('data-variant="trace"');
    expect(html).toContain('macro');
    expect(html).toContain('no calls emitted'); // inputs is a typed gap
  });

  it('says unavailable, not zero bars, when the trace could not be read', () => {
    const html = renderToStaticMarkup(createElement(PipelineTimelineView, { result: { state: 'unavailable', events: [] } }));
    expect(html).toContain('Call trace unavailable');
    expect(html).not.toContain('data-variant="trace"');
  });

  it('says "N placed of M" when some events map to no stage', () => {
    expect(timelineCallsLabel({ calls: 3, unmapped: 2 })).toBe('3 placed of 5 calls');
    expect(timelineCallsLabel({ calls: 3, unmapped: 0 })).toBe('3 calls');
    const stray = { ...event, phase: 'zzz-unknown', document_key: null, name: 'mystery', event_kind: 'zzz' } as unknown as PipelineRunEvent;
    const built = buildPipelineTimeline([event, stray]);
    const html = renderToStaticMarkup(createElement(PipelineTimelineView, { result: { state: 'available', events: [event, stray] } }));
    expect(html).toContain(timelineCallsLabel(built));
    if (built.unmapped > 0) expect(html).toContain('not mapped to a stage');
  });

  it('distinguishes not-recorded', () => {
    const html = renderToStaticMarkup(createElement(PipelineTimelineView, { result: { state: 'not-recorded', events: [] } }));
    expect(html).toContain('No calls recorded');
  });
});
