import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { TodayActionsPanel } from './today-actions-panel';
import type { RebalanceAction } from '@/lib/types';

function render(actions: RebalanceAction[]): string {
  return renderToStaticMarkup(createElement(TodayActionsPanel, { actions }));
}

describe('TodayActionsPanel', () => {
  it('shows the no-rebalance state when there are no actions', () => {
    expect(render([])).toContain('No rebalance proposed');
  });

  it('shows the at-target state when every action is HOLD', () => {
    const html = render([
      { ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' },
      { ticker: 'GLD', current_pct: 50, recommended_pct: 50, action: 'HOLD' },
    ]);
    expect(html).toContain('No changes proposed');
    expect(html).toContain('2 positions held');
  });

  it('renders changes with ticker, weights, and a delta', () => {
    const html = render([
      { ticker: 'NVDA', current_pct: 0, recommended_pct: 6.5, action: 'OPEN' },
    ]);
    expect(html).toContain('NVDA');
    expect(html).toContain('OPEN');
    expect(html).toContain('0.0%');
    expect(html).toContain('6.5%');
    expect(html).toContain('+6.5pp');
  });

  it('orders EXIT before ADD (decision-first sort)', () => {
    const html = render([
      { ticker: 'AAA', current_pct: 1, recommended_pct: 2, action: 'ADD' },
      { ticker: 'ZZZ', current_pct: 3, recommended_pct: 0, action: 'EXIT' },
    ]);
    expect(html.indexOf('ZZZ')).toBeLessThan(html.indexOf('AAA'));
  });
});
