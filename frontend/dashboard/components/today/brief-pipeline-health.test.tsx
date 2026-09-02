import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { AtlasRunDiagnostics } from '@/lib/types';
import {
  BriefPipelineHealth,
  buildLatestRunCards,
  type BriefRunHealth,
} from './brief-pipeline-health';

vi.mock('next/link', () => ({
  default: (props: { children?: unknown; href?: string }) => props.children,
}));

function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
  return {
    run_id: 'r',
    run_type: 'delta',
    run_date: '2026-08-27',
    model: null,
    status: 'ok',
    started_at: null,
    finished_at: '2026-08-27T12:00:00Z',
    duration_s: 1844,
    llm_calls: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    cached_tokens: null,
    search_calls: null,
    grounding_ok: null,
    grounding_failed: null,
    est_cost_usd: null,
    segments_total: 27,
    segments_ok: 15,
    segments_carried: 12,
    segments_failed: 0,
    error_summary: null,
    breakdown: null,
    created_at: '2026-08-27T12:00:00Z',
    ...o,
  };
}

const runHealth: BriefRunHealth = {
  status: 'degraded',
  runDate: '2026-08-27',
  finishedAt: '2026-08-27T12:00:00Z',
  segmentsOk: 15,
  segmentsTotal: 27,
  segmentsCarried: 12,
  segmentsFailed: 0,
  durationS: 1844,
};

describe('buildLatestRunCards', () => {
  it('always includes duration and segment counts; omits tokens/calls when absent', () => {
    const cards = buildLatestRunCards(runHealth, diag({ model: 'gpt-test' }));
    const labels = cards.map((c) => c.label);
    expect(labels).toEqual(['Duration', 'Segments', 'Carry', 'Fail', 'Model']);
    expect(cards.find((c) => c.label === 'Duration')?.value).toMatch(/30m/);
    expect(cards.find((c) => c.label === 'Segments')?.value).toBe('15/27');
    expect(labels).not.toContain('Tokens');
    expect(labels).not.toContain('Calls');
    expect(labels).not.toContain('Error');
  });

  it('appends call/token/error tiles only when present on the diagnostic row', () => {
    const cards = buildLatestRunCards(
      runHealth,
      diag({
        llm_calls: 42,
        total_tokens: 12000,
        error_summary: 'timeout on segment 3',
      })
    );
    expect(cards.map((c) => c.label)).toContain('Calls');
    expect(cards.map((c) => c.label)).toContain('Tokens');
    expect(cards.map((c) => c.label)).toContain('Error');
    expect(cards.find((c) => c.label === 'Tokens')?.value).toBe('12,000');
  });
});

describe('BriefPipelineHealth', () => {
  it('folds summary cards and a one-week bar into the Pipeline health panel', () => {
    const diagnostics = [
      diag({ run_date: '2026-08-25', created_at: '2026-08-25T10:00:00Z' }),
      diag({ run_date: '2026-08-27', created_at: '2026-08-27T10:00:00Z' }),
    ];
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics,
        initialWeekStart: '2026-08-24',
      })
    );

    expect(html).toContain('data-testid="brief-pipeline-health"');
    expect(html).toContain('Pipeline health');
    expect(html).toContain('Pipeline completed with carry');
    expect(html).toContain('data-testid="brief-pipeline-summary"');
    expect(html).toContain('Duration');
    expect(html).toContain('15/27');
    expect(html).toContain('data-testid="brief-run-health-week"');
    expect(html).toContain('Aug 24–30');
    expect(html).toContain('Previous week');
    expect(html).toContain('Next week');
    // Empty days in the week render dashed boxes
    expect(html).toContain('week-day-empty-2026-08-24');
    expect(html).toContain('week-day-empty-2026-08-26');
    expect(html).toContain('week-day-2026-08-25');
    expect(html).toContain('week-day-2026-08-27');
    // Standalone full-history strip label must not appear here
    expect(html).not.toContain('brief-run-health-timeline');
  });

  it('notes when a position date is newer than the committed snapshot', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics: [diag()],
        snapshotDate: '2026-08-27',
        positionDates: ['2026-08-31', '2026-08-27'],
      })
    );
    expect(html).toContain('data-testid="unpublished-book-note"');
    expect(html).toContain('Last committed snapshot is 2026-08-27');
    expect(html).toContain('Newer positions are hidden until a snapshot exists for that date');
  });

  it('does not claim hidden positions when no book date is newer than the snapshot', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics: [diag()],
        snapshotDate: '2026-08-28',
        positionDates: ['2026-08-28', '2026-08-27'],
      })
    );
    expect(html).not.toContain('data-testid="unpublished-book-note"');
  });

  it('keys the unpublished note to the snapshot, not pipeline runHealth', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth: { ...runHealth, runDate: '2026-08-31' },
        diagnostics: [diag({ run_date: '2026-08-31' })],
        snapshotDate: '2026-08-28',
        positionDates: ['2026-08-28', '2026-08-27'],
      })
    );
    expect(html).not.toContain('data-testid="unpublished-book-note"');
  });

  it('defaults the week window to the current week of `now`', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics: [diag()],
        now: new Date('2026-08-27T15:00:00Z'),
      })
    );
    expect(html).toContain('Aug 24–30');
  });

  it('fails honest when history is missing', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth: null,
        diagnostics: [],
      })
    );
    expect(html).toContain('Pipeline status unavailable');
    expect(html).toContain('Run history unavailable');
    expect(html).not.toContain('data-testid="brief-run-health-week"');
    expect(html).not.toContain('data-testid="brief-pipeline-summary"');
  });

  it('exposes week navigation controls for stepping by weekly blocks', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics: [diag()],
        initialWeekStart: '2026-08-24',
        now: new Date('2026-09-03T12:00:00Z'), // later week so Next stays enabled
      })
    );
    expect(html).toMatch(/aria-label="Previous week"/);
    expect(html).toMatch(/aria-label="Next week"/);
    expect(html).toMatch(/aria-label="Next week"[^>]*aria-disabled="false"/);
    expect(html).not.toMatch(/aria-label="Next week"[^>]*aria-disabled="true"/);
  });

  it('disables next-week when the pager is already on the current week', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics: [diag()],
        initialWeekStart: '2026-08-24',
        now: new Date('2026-08-27T15:00:00Z'),
      })
    );
    expect(html).toMatch(/aria-label="Next week"[^>]*aria-disabled="true"/);
    expect(html).toMatch(/aria-label="Next week"[^>]*\sdisabled(?:=|\s|>)/);
    expect(html).toContain('Aug 24–30');
  });

  it('clamps a future initialWeekStart down to the current week', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics: [diag()],
        initialWeekStart: '2026-09-07',
        now: new Date('2026-08-27T15:00:00Z'),
      })
    );
    expect(html).toContain('Aug 24–30');
    expect(html).not.toContain('Sep 7');
  });

  it('uses matching box-border pill chrome for empty and filled day slots', () => {
    const html = renderToStaticMarkup(
      createElement(BriefPipelineHealth, {
        runHealth,
        diagnostics: [
          diag({ run_date: '2026-08-25', created_at: '2026-08-25T10:00:00Z' }),
        ],
        initialWeekStart: '2026-08-24',
        now: new Date('2026-08-27T15:00:00Z'),
      })
    );
    // Shared layout classes keep dashed empty pills aligned with filled ones
    expect(html).toMatch(
      /data-testid="week-day-empty-2026-08-24"[^>]*box-border[^>]*block[^>]*h-2\.5[^>]*w-full[^>]*border/
    );
    expect(html).toMatch(
      /data-testid="week-day-2026-08-25"[^>]*box-border[^>]*block[^>]*h-2\.5[^>]*w-full[^>]*border/
    );
    expect(html).toContain('border-transparent');
    expect(html).toContain('border-dashed');
  });
});
