import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { formatDuration, RunEconomicsRow } from './run-economics-row';
import type { AtlasRunDiagnostics } from '@/lib/types';

function diag(o: Partial<AtlasRunDiagnostics>): AtlasRunDiagnostics {
  return {
    run_id: 'r', run_type: 'baseline', run_date: '2026-06-23', model: null, status: 'ok',
    started_at: null, finished_at: null, duration_s: null, llm_calls: 163,
    prompt_tokens: null, completion_tokens: null, total_tokens: 1_640_000, cached_tokens: 639_600,
    search_calls: null, grounding_ok: 31, grounding_failed: 0, est_cost_usd: 0.616,
    segments_total: 27, segments_ok: 27, segments_carried: 0, segments_failed: 0,
    error_summary: null, breakdown: null, created_at: '2026-06-23T16:58:51Z', ...o,
  };
}

describe('run-economics formatting', () => {
  it('formats run duration compactly', () => {
    expect(formatDuration(154)).toBe('2m 34s');
    expect(formatDuration(42)).toBe('42s');
  });

  it('renders the public run-health values in a padded responsive grid', () => {
    const html = renderToStaticMarkup(
      createElement(RunEconomicsRow, {
        latest: diag({
          duration_s: 154,
          segments_total: 27,
          segments_ok: 24,
          segments_carried: 2,
          segments_failed: 1,
        }),
      }),
    );

    expect(html).toContain('Duration');
    expect(html).toContain('2m 34s');
    expect(html).toContain('Segments produced');
    expect(html).toContain('24/27');
    expect(html).toContain('Carried');
    expect(html).toContain('Failed');
    expect(html).toContain('grid-cols-2');
    expect(html).toContain('md:grid-cols-4');
    expect(html).toContain('p-4');
  });
});
