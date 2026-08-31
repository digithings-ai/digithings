import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { TableRow } from '@/lib/database.types';
import AttributionWorkspace, {
  decisionsForAnalysisPeriod,
  filterDecisionsByPeriod,
} from './AttributionWorkspace';

function decision(over: Partial<TableRow<'decision_log'>>): TableRow<'decision_log'> {
  return {
    id: 'decision-1',
    run_id: 'run-1',
    run_date: '2026-07-01',
    ticker: 'AAA',
    stance: 'buy',
    conviction: 3,
    thesis: 'Demand remains durable.',
    benchmark: 'SPY',
    holding_days: 5,
    status: 'resolved',
    actual_return: 0.04,
    alpha: 0.02,
    reflection: 'The catalyst arrived inside the expected window.',
    resolved_at: '2026-07-08T16:00:00Z',
    created_at: '2026-07-01T16:00:00Z',
    ...over,
  };
}

describe('AttributionWorkspace', () => {
  it('defaults to the compact decision-effectiveness view', () => {
    const decisions = [
      decision({ id: 'buy-win', ticker: 'AAA', alpha: 0.03 }),
      decision({ id: 'sell-win', ticker: 'BBB', stance: 'sell', alpha: -0.02 }),
    ];

    const html = renderToStaticMarkup(
      createElement(AttributionWorkspace, {
        attribution: [],
        attributionDate: '2026-07-31',
        decisions,
      })
    );

    expect(html).toContain('Decision effectiveness');
    expect(html).toContain('Book attribution');
    expect(html).toContain('Audit');
    expect(html).toContain('2 scored decisions · limited sample');
    expect(html).not.toContain('sample confidence');
    expect(html).toContain('Mean decision edge');
    expect(html).toContain('Directional hit rate');
    expect(html).toContain('correct directional calls');
    expect(html).toContain('Edge consistency');
    expect(html).toContain('mean edge / variability');
    expect(html).not.toContain('Information ratio');
    expect(html).not.toContain('decisions above benchmark');
    expect(html).toContain('Decisions scored');
    expect(html).toContain('Decision edge over time');
    expect(html).toContain('Review queue');
    expect(html).toContain('Analysis period');
    expect(html).toContain('From inception');
    expect(html).toContain('1W');
    expect(html).toContain('1M');
    expect(html).toContain('YTD');
    expect(html).toContain('all scored decisions in period');
    expect(html).not.toContain('Rolling window');
    expect(html).not.toMatch(/(?:10|20|40) calls/);
    expect(html).not.toContain('episode');
    expect(html).not.toContain('Demand remains durable.');
  });

  it('scopes decision history relative to the latest available decision date', () => {
    const decisions = [
      decision({ id: 'prior-year', run_date: '2025-12-31' }),
      decision({ id: 'ytd-start', run_date: '2026-01-01' }),
      decision({ id: 'before-three-months', run_date: '2026-05-04' }),
      decision({ id: 'three-months', run_date: '2026-05-05' }),
      decision({ id: 'before-one-month', run_date: '2026-07-04' }),
      decision({ id: 'one-month', run_date: '2026-07-05' }),
      decision({ id: 'before-one-week', run_date: '2026-07-28' }),
      decision({ id: 'one-week', run_date: '2026-07-29' }),
      decision({ id: 'latest', run_date: '2026-08-05' }),
    ];

    expect(filterDecisionsByPeriod(decisions, 'ytd').map((row) => row.id)).toEqual([
      'ytd-start',
      'before-three-months',
      'three-months',
      'before-one-month',
      'one-month',
      'before-one-week',
      'one-week',
      'latest',
    ]);
    expect(filterDecisionsByPeriod(decisions, '3m').map((row) => row.id)).toEqual([
      'three-months',
      'before-one-month',
      'one-month',
      'before-one-week',
      'one-week',
      'latest',
    ]);
    expect(filterDecisionsByPeriod(decisions, '1m').map((row) => row.id)).toEqual([
      'one-month',
      'before-one-week',
      'one-week',
      'latest',
    ]);
    expect(filterDecisionsByPeriod(decisions, '1w').map((row) => row.id)).toEqual([
      'one-week',
      'latest',
    ]);
    expect(filterDecisionsByPeriod(decisions, '1y')).toHaveLength(9);
    expect(filterDecisionsByPeriod(decisions, 'all')).toBe(decisions);
  });

  it('does not promote an overlapping update into a new decision at a period boundary', () => {
    const decisions = [
      decision({
        id: 'initiating-call',
        ticker: 'AAA',
        run_date: '2025-12-31',
        holding_days: 10,
      }),
      decision({
        id: 'repeat-update',
        ticker: 'AAA',
        run_date: '2026-01-02',
        holding_days: 10,
      }),
      decision({ id: 'new-call', ticker: 'BBB', run_date: '2026-02-01' }),
      decision({
        id: 'pending',
        ticker: 'CCC',
        run_date: '2026-08-05',
        status: 'pending',
        alpha: null,
      }),
    ];

    expect(decisionsForAnalysisPeriod(decisions, 'ytd').map((row) => row.id)).toEqual([
      'new-call',
      'pending',
    ]);
  });
});