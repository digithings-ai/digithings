import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import ThesesTab from './ThesesTab';
import type { Position, Thesis } from '@/lib/types';
import type { TableRow } from '@/lib/database.types';
import type { ThesisVehicleRow } from '@/lib/thesis-story';

const thesis = (over: Partial<Thesis>): Thesis => ({
  id: 'MT1', name: 'Market view', vehicle: null, invalidation: null, status: 'ACTIVE',
  notes: null, confidence: null, horizon: null, thesis_kind: 'market',
  validation_criteria: [], invalidation_criteria: [], linked_market_thesis_id: null, ...over,
});

const position = (over: Partial<Position>): Position => ({
  ticker: 'AAA', name: 'Alpha ETF', type: 'LONG', weight_actual: 20, current_price: 100,
  entry_price: 90, entry_date: '2026-05-01', rationale: '', thesis_ids: [], category: 'equity',
  pm_notes: '', stats: {}, since_entry_return_pct: 5.5, stop_loss_pct: -8, target_pct_gain: 15,
  horizon_days: 90, ...over,
});

const decision = (over: Partial<TableRow<'decision_log'>>): TableRow<'decision_log'> =>
  ({
    id: 'd', run_id: 'r', run_date: '2026-06-26', ticker: 'AAA', stance: 'buy', conviction: 3,
    thesis: null, benchmark: 'SPY', holding_days: 5, status: 'resolved', actual_return: 0.01,
    alpha: 0.001, reflection: null, resolved_at: null, created_at: null, ...over,
  }) as TableRow<'decision_log'>;

const base = {
  lastUpdated: '2026-07-17',
  positions: [
    position({ ticker: 'AAA', weight_actual: 20 }),
    position({ ticker: 'TLT', name: 'Long Treasuries', weight_actual: 12 }),
    position({ ticker: 'CASH', name: 'Cash', weight_actual: 5 }),
  ],
  theses: [
    thesis({
      id: 'MT1', name: 'Advanced Materials Growth', confidence: 0.8, horizon: 'long_term',
      notes: 'Materials demand is rising.', validation_criteria: ['Prices firm'],
      invalidation_criteria: ['Demand rolls over'],
    }),
    thesis({ id: 'MT2', name: 'USD Strength', confidence: 0.6 }),
  ],
  decisions: [decision({ ticker: 'AAA', conviction: 3 })],
  thesisVehicleRows: [
    { date: '2026-07-17', thesisId: 'MT1', ticker: 'AAA', rationale: 'AAA expresses the growth view', candidateRank: 1 },
    { date: '2026-07-17', thesisId: 'MT1', ticker: 'BBB', rationale: 'BBB is a secondary candidate', candidateRank: 2 },
  ] as ThesisVehicleRow[],
};

describe('ThesesTab (story spine)', () => {
  const html = renderToStaticMarkup(createElement(ThesesTab, base));

  it('renders the market thesis header with confidence and criteria', () => {
    expect(html).toContain('Advanced Materials Growth');
    expect(html).toContain('80% confidence');
    expect(html).toContain('What confirms this');
    expect(html).toContain('Prices firm');
  });

  it('keeps confidence and timeframe inside the disclosure body, not its summary', () => {
    const summary = html.match(/<summary[^>]*>([\s\S]*?)<\/summary>/)?.[1] ?? '';
    expect(summary).toContain('Advanced Materials Growth');
    expect(summary).not.toContain('80% confidence');
    expect(summary).not.toContain('long_term');
    expect(html).toContain('80% confidence');
    expect(html).toContain('Long term');
  });

  it('renders vehicles from the thesis_vehicles join with rationale and rank', () => {
    expect(html).toContain('AAA expresses the growth view');
    expect(html).toContain('#1 pick');
  });

  it('does not present vehicle mapping as book-attribution coverage', () => {
    expect(html).not.toContain('drives');
    expect(html).not.toContain('mapped exposure');
  });

  it('renders the latest signed analyst call', () => {
    expect(html).toContain('+3'); // SignedConvictionBadge(3)
    expect(html).toContain('as of Jun 26'); // AsOfBadge from decision run_date, not now
  });

  it('links a vehicle to its dossier route', () => {
    expect(html).toContain('/portfolio/tickers?ticker=AAA');
  });

  it('does not render unassigned holding or proposal buckets', () => {
    expect(html).not.toContain('Not tied to a market view');
    expect(html).not.toContain('Proposed, not held');
    expect(html).not.toContain('>TLT<');
  });

  it('shows only nonterminal opinions in Research views', () => {
    const terminalHtml = renderToStaticMarkup(createElement(ThesesTab, {
      ...base,
      theses: [
        thesis({ id: 'ACTIVE', name: 'Active opinion', status: 'ACTIVE' }),
        thesis({ id: 'CLOSED', name: 'Closed opinion', status: 'CLOSED' }),
        thesis({ id: 'INVALID', name: 'Invalidated opinion', status: 'INVALIDATED' }),
      ],
    }));
    expect(terminalHtml).toContain('Active opinion');
    expect(terminalHtml).not.toContain('Closed opinion');
    expect(terminalHtml).not.toContain('Invalidated opinion');
  });

  it('renders one active view per durable topic key', () => {
    const duplicateHtml = renderToStaticMarkup(createElement(ThesesTab, {
      ...base,
      theses: [
        { ...thesis({ id: 'CTA-NEW', name: 'CTA positioning', confidence: 0.8 }), topic_key: 'cta-positioning' } as Thesis,
        { ...thesis({ id: 'CTA-OLD', name: 'CTA volatility', confidence: 0.6 }), topic_key: 'cta-positioning' } as Thesis,
        { ...thesis({ id: 'CHINA', name: 'China recovery', confidence: 0.7 }), topic_key: 'china-recovery' } as Thesis,
      ],
    }));

    expect(duplicateHtml).toContain('CTA positioning');
    expect(duplicateHtml).not.toContain('CTA volatility');
    expect(duplicateHtml).toContain('China recovery');
  });
});
