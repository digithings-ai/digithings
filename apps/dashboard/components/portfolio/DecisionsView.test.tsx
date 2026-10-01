import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { TableRow } from '@/lib/database.types';
import DecisionsView from './DecisionsView';

function decision(over: Partial<TableRow<'decision_log'>>): TableRow<'decision_log'> {
  return {
    id: 'd1', run_id: 'r', run_date: '2026-07-01', ticker: 'AAA', stance: 'buy', conviction: 3,
    thesis: 'Demand remains durable.', benchmark: 'SPY', holding_days: 5, status: 'resolved',
    actual_return: 0.04, alpha: 0.02, reflection: 'r', resolved_at: '2026-07-08T16:00:00Z',
    created_at: '2026-07-01T16:00:00Z', ...over,
  };
}

const two = [
  decision({ id: 'buy-win', ticker: 'AAA', alpha: 0.03 }),
  decision({ id: 'sell-win', ticker: 'BBB', stance: 'sell', alpha: -0.02, run_date: '2026-07-10' }),
];

const render = (props: Partial<Parameters<typeof DecisionsView>[0]> = {}) =>
  renderToStaticMarkup(
    createElement(DecisionsView, { decisions: two, pane: 'edge', onPaneChange: () => {}, ...props })
  );

describe('DecisionsView', () => {
  it('leads with the verdict, stats and the edge charts on the edge pane', () => {
    const html = render();
    expect(html).toContain('Decision monitor');
    expect(html).toContain('Positive decision edge');
    expect(html).toContain('2 scored decisions · limited sample');
    expect(html).toContain('Mean decision edge');
    expect(html).toContain('Directional hit rate');
    expect(html).toContain('Edge consistency');
    expect(html).toContain('Decisions scored');
    expect(html).toContain('Decision edge over time');
    expect(html).toContain('data-testid="decision-edge-trend"');
    expect(html).toContain('data-slot="sparkline"');
    expect(html).toContain('Edge by conviction');
    expect(html).toContain('Edge by stance');
    expect(html).toContain('Review queue');
    expect(html).toContain('Analysis period');
    expect(html).toContain('From inception');
    expect(html).not.toContain('Demand remains durable.');
  });

  it('gives the trend an aria summary and uses the health vocabulary for the verdict', () => {
    const html = render();
    expect(html).toContain('Cumulative mean decision edge across 2 dates');
    expect(html).toContain('text-accent');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });

  it('warns, in words, on a negative edge', () => {
    const html = render({ decisions: [decision({ alpha: -0.03 }), decision({ id: 'd2', ticker: 'BBB', alpha: -0.01 })] });
    expect(html).toContain('Negative decision edge');
    expect(html).toContain('text-warn');
  });

  it('shows an empty state without scored decisions', () => {
    const html = render({ decisions: [] });
    expect(html).toContain('Awaiting resolved outcomes');
    expect(html).toContain('No resolved directional decisions are available yet.');
  });

  it('hides the Theses segment unless a theses pane is supplied', () => {
    expect(render()).not.toContain('>Theses<');
    const html = render({ pane: 'theses', thesesPane: createElement('div', { id: 'spine' }, 'SPINE') });
    expect(html).toContain('>Theses<');
    expect(html).toContain('SPINE');
    expect(html).not.toContain('Edge by stance');
  });

  it('falls back to the edge pane when theses are requested but absent', () => {
    expect(render({ pane: 'theses' })).toContain('Edge by stance');
  });

  it('renders the audit pane with the period-scoped record', () => {
    const html = render({ pane: 'audit' });
    expect(html).not.toContain('Edge by stance');
    expect(html).toContain('Analysis period');
  });
});
