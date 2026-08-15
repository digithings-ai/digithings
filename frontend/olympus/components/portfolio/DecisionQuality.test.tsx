import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import type { TableRow } from '@/lib/database.types';
import DecisionQuality from './DecisionQuality';

function decision(over: Partial<TableRow<'decision_log'>>): TableRow<'decision_log'> {
  return {
    id: '1',
    ticker: 'AAA',
    date: '2026-06-01',
    run_date: '2026-06-01',
    status: 'resolved',
    stance: 'bullish',
    conviction: 4,
    alpha: 0.05,
    actual_return: 0.06,
    thesis: null,
    reflection: null,
    ...over,
  } as unknown as TableRow<'decision_log'>;
}

describe('DecisionQuality', () => {
  it('renders the calibration scorecard from injected decisions', () => {
    const decisions = [
      decision({ id: '1', ticker: 'NVDA', conviction: 5, alpha: 0.08 }),
      decision({ id: '2', ticker: 'SPY', conviction: 1, alpha: 0.01 }),
    ];
    const html = renderToStaticMarkup(createElement(DecisionQuality, { decisions }));
    expect(html).toContain('Decision quality');
    expect(html).toContain('Conviction calibration'); // section from the scorecard
    expect(html).toContain('Calibration'); // the conviction→alpha verdict tile
  });

  it('shows the empty state when no decisions have resolved', () => {
    const html = renderToStaticMarkup(createElement(DecisionQuality, { decisions: [] }));
    expect(html).toContain('Decision quality');
    expect(html).toContain('No resolved decisions yet');
  });
});
