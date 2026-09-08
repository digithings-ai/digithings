import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { TableRow } from '@/lib/database.types';
import DecisionAudit from './DecisionAudit';

function decision(index: number): TableRow<'decision_log'> {
  const day = String(index + 1).padStart(2, '0');
  return {
    id: `decision-${index}`,
    run_id: `run-${index}`,
    run_date: `2026-07-${day}`,
    ticker: `T${day}`,
    stance: index % 2 === 0 ? 'buy' : 'sell',
    conviction: 3,
    thesis: `Thesis ${day}`,
    benchmark: 'SPY',
    holding_days: 5,
    status: 'resolved',
    actual_return: 0.02,
    alpha: index % 2 === 0 ? 0.01 : -0.01,
    reflection: `Reflection ${day}`,
    resolved_at: `2026-08-${day}T16:00:00Z`,
    created_at: `2026-07-${day}T16:00:00Z`,
  };
}

describe('DecisionAudit', () => {
  it('renders a searchable 25-row page while preserving raw alpha and reasoning', () => {
    const html = renderToStaticMarkup(
      createElement(DecisionAudit, {
        decisions: Array.from({ length: 30 }, (_, index) => decision(index)),
      })
    );

    expect(html).toContain('Search decisions');
    expect(html).toContain('Filter by stance');
    expect(html).toContain('Filter by status');
    expect(html).toContain('Raw alpha');
    expect(html).toContain('Decision edge');
    expect(html).toContain('Thesis 30');
    expect(html).toContain('Reflection 30');
    expect(html.match(/data-audit-row="true"/g)).toHaveLength(25);
    expect(html).toContain('1–25 of 30');
    expect(html).not.toContain('Thesis 05');
  });
});