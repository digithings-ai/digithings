import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { VehicleExpressionRow } from './VehicleExpressionRow';
import type { Position } from '@/lib/types';
import type { DecisionLogRow } from '@/lib/holdings-decisions';

const position = (over: Partial<Position> = {}): Position => ({
  ticker: 'AAA',
  name: 'Alpha ETF',
  type: 'LONG',
  weight_actual: 20,
  current_price: 100,
  entry_price: 90,
  entry_date: '2026-05-01',
  rationale: '',
  thesis_ids: [],
  category: 'equity',
  pm_notes: '',
  stats: {},
  since_entry_return_pct: 5.5,
  stop_loss_pct: -8,
  target_pct_gain: 15,
  horizon_days: 90,
  ...over,
});

const decision = (over: Partial<DecisionLogRow> = {}): DecisionLogRow =>
  ({
    id: 'd',
    run_id: 'r',
    run_date: '2026-06-26',
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

describe('VehicleExpressionRow — no nested glass-card', () => {
  it('does not wrap vehicle rows in a glass-card inside the details element', () => {
    const html = renderToStaticMarkup(
      createElement(VehicleExpressionRow, {
        ticker: 'AAA',
        rationale: 'Test rationale',
        candidateRank: 1,
        position: position(),
        latestDecision: decision(),
        dossierHref: '/portfolio/tickers?ticker=AAA',
        deliberationHref: '/pipeline',
      })
    );

    // The vehicle row should render as a native <details> without nested glass-card styling
    // The parent (ThesisStoryCard) wraps vehicles in a glass-card, but individual rows should not
    expect(html).toContain('<details');
    expect(html).not.toMatch(/<details[^>]*class="[^"]*glass-card/);
  });

  it('uses canonical text-xs for labels instead of ad-hoc text-[10px]', () => {
    const html = renderToStaticMarkup(
      createElement(VehicleExpressionRow, {
        ticker: 'AAA',
        rationale: 'Test rationale',
        candidateRank: 1,
        position: position(),
        latestDecision: decision(),
        dossierHref: '/portfolio/tickers?ticker=AAA',
        deliberationHref: '/pipeline',
      })
    );

    // Check that labels use text-xs instead of text-[10px]
    expect(html).toContain('text-xs');
    // The "Latest call" label should not use text-[10px]
    const latestCallSection = html.split('Latest call')[0] + 'Latest call' + html.split('Latest call')[1];
    expect(latestCallSection).not.toContain('text-[10px]');
  });
});
