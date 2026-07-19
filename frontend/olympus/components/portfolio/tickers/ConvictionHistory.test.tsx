import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import ConvictionHistory from './ConvictionHistory';
import type { DecisionLogRow } from '@/lib/holdings-decisions';

const decision = (id: string, date: string, over: Partial<DecisionLogRow> = {}): DecisionLogRow =>
  ({
    id,
    run_id: 'r',
    run_date: date,
    ticker: 'AAA',
    stance: 'buy',
    conviction: 3,
    thesis: null,
    benchmark: 'SPY',
    holding_days: 5,
    status: 'resolved',
    actual_return: 0.01,
    alpha: 0.001,
    reflection: null,
    resolved_at: null,
    created_at: null,
    ...over,
  }) as DecisionLogRow;

describe('ConvictionHistory — bounded display with reveal', () => {
  it('shows at most 6 recent rows by default when there are more than 6 decisions', () => {
    const decisions = [
      decision('d1', '2026-01-01'),
      decision('d2', '2026-02-01'),
      decision('d3', '2026-03-01'),
      decision('d4', '2026-04-01'),
      decision('d5', '2026-05-01'),
      decision('d6', '2026-06-01'),
      decision('d7', '2026-07-01'),
      decision('d8', '2026-08-01'),
    ];

    const html = renderToStaticMarkup(createElement(ConvictionHistory, { decisions }));

    // Count <tr> elements in the HTML (1 header + data rows)
    const trMatches = html.match(/<tr[^>]*>/g) || [];
    // Expect at most 7 rows (1 header + 6 data rows) to be visible initially
    expect(trMatches.length).toBeLessThanOrEqual(7);
  });

  it('shows a "Show N older" button when more than 6 decisions exist', () => {
    const decisions = [
      decision('d1', '2026-01-01'),
      decision('d2', '2026-02-01'),
      decision('d3', '2026-03-01'),
      decision('d4', '2026-04-01'),
      decision('d5', '2026-05-01'),
      decision('d6', '2026-06-01'),
      decision('d7', '2026-07-01'),
      decision('d8', '2026-08-01'),
    ];

    const html = renderToStaticMarkup(createElement(ConvictionHistory, { decisions }));

    // Should show a button to reveal older rows
    expect(html).toMatch(/Show \d+ older/);
  });

  it('shows all decisions (no button) when there are 6 or fewer', () => {
    const decisions = [
      decision('d1', '2026-01-01'),
      decision('d2', '2026-02-01'),
      decision('d3', '2026-03-01'),
    ];

    const html = renderToStaticMarkup(createElement(ConvictionHistory, { decisions }));

    // Should not show the expand button
    expect(html).not.toMatch(/Show \d+ older/);

    // All rows should be visible (1 header + 3 data rows)
    const trMatches = html.match(/<tr[^>]*>/g) || [];
    expect(trMatches.length).toBe(4);
  });
});
