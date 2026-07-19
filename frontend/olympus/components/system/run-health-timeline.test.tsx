import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RunHealthTimeline } from './run-health-timeline';
import type { AtlasRunDiagnostics } from '@/lib/types';

function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
  return {
    run_id: 'r',
    run_type: 'baseline',
    run_date: '2026-06-23',
    model: null,
    status: 'ok',
    started_at: null,
    finished_at: '2026-06-23T16:58:51Z',
    duration_s: null,
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
    segments_ok: 27,
    segments_carried: 0,
    segments_failed: 0,
    error_summary: null,
    breakdown: null,
    created_at: '2026-06-23T16:58:51Z',
    ...o,
  };
}

describe('RunHealthTimeline', () => {
  it('renders nothing when diagnostics list is empty', () => {
    const html = renderToStaticMarkup(createElement(RunHealthTimeline, { diagnostics: [] }));
    expect(html).toBe('');
  });

  it('renders a horizontal timeline with chronological order (oldest left, newest right)', () => {
    const diagnostics = [
      diag({ run_id: 'day3', run_date: '2026-06-25', created_at: '2026-06-25T10:00:00Z', status: 'ok' }),
      diag({ run_id: 'day2', run_date: '2026-06-24', created_at: '2026-06-24T10:00:00Z', status: 'ok' }),
      diag({ run_id: 'day1', run_date: '2026-06-23', created_at: '2026-06-23T10:00:00Z', status: 'ok' }),
    ];
    const html = renderToStaticMarkup(createElement(RunHealthTimeline, { diagnostics }));

    // Should not have the old vertical list pattern with <ol>
    expect(html).not.toContain('<ol');

    // Should contain horizontal timeline elements
    expect(html).toContain('Run health');

    // Check for chronological ordering: day1, day2, day3 appear in that sequence
    const day1Index = html.indexOf('2026-06-23');
    const day2Index = html.indexOf('2026-06-24');
    const day3Index = html.indexOf('2026-06-25');
    expect(day1Index).toBeGreaterThan(0);
    expect(day2Index).toBeGreaterThan(day1Index);
    expect(day3Index).toBeGreaterThan(day2Index);
  });

  it('applies correct color classes for different outcomes', () => {
    const diagnostics = [
      diag({ run_id: 'ok', run_date: '2026-06-23', status: 'ok' }),
      diag({ run_id: 'recovered1', run_date: '2026-06-24', status: 'failed', created_at: '2026-06-24T09:00:00Z' }),
      diag({ run_id: 'recovered2', run_date: '2026-06-24', status: 'ok', created_at: '2026-06-24T10:00:00Z' }),
      diag({ run_id: 'failed', run_date: '2026-06-25', status: 'failed' }),
    ];
    const html = renderToStaticMarkup(createElement(RunHealthTimeline, { diagnostics }));

    // ok → bg-accent (green)
    expect(html).toContain('bg-accent');

    // recovered → bg-warn variants (orange)
    expect(html).toMatch(/bg-warn/);

    // failed → bg-down (red)
    expect(html).toContain('bg-down');
  });

  it('provides accessible segment labels with outcome information', () => {
    const diagnostics = [
      diag({ run_id: 'success', run_date: '2026-06-23', status: 'ok' }),
      diag({ run_id: 'fail', run_date: '2026-06-24', status: 'failed', error_summary: 'Connection timeout' }),
    ];
    const html = renderToStaticMarkup(createElement(RunHealthTimeline, { diagnostics }));

    // Each segment should be a button with aria-label
    expect(html).toMatch(/aria-label="[^"]*2026-06-23[^"]*"/);
    expect(html).toMatch(/aria-label="[^"]*2026-06-24[^"]*"/);
    expect(html).toMatch(/aria-label="[^"]*ok[^"]*"/i);
    expect(html).toMatch(/aria-label="[^"]*failed[^"]*"/i);
  });

  it('includes tooltip triggers for detailed information', () => {
    const diagnostics = [
      diag({
        run_date: '2026-06-23',
        run_type: 'baseline',
        status: 'ok',
        duration_s: 45.2,
        segments_total: 27,
        segments_ok: 27,
      }),
    ];
    const html = renderToStaticMarkup(createElement(RunHealthTimeline, { diagnostics }));

    // Tooltip trigger should be present (SSR emits the wiring)
    expect(html).toContain('tooltip-trigger');
  });

  it('exposes retry attempt count and error summary in tooltip-accessible content', () => {
    const diagnostics = [
      diag({ run_date: '2026-06-23', status: 'failed', created_at: '2026-06-23T09:00:00Z' }),
      diag({ run_date: '2026-06-23', status: 'ok', created_at: '2026-06-23T10:00:00Z' }),
    ];
    const html = renderToStaticMarkup(createElement(RunHealthTimeline, { diagnostics }));

    // Should mention attempts > 1 in accessible content
    expect(html).toMatch(/2\s*attempt/i);
  });

  it('includes a legend for color semantics', () => {
    const diagnostics = [diag({ run_date: '2026-06-23', status: 'ok' })];
    const html = renderToStaticMarkup(createElement(RunHealthTimeline, { diagnostics }));

    expect(html).toMatch(/successful|success/i);
    expect(html).toMatch(/recovered|degraded/i);
    expect(html).toMatch(/failed/i);
  });
});
