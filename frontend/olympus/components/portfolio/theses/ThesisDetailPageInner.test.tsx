import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { DashboardData, Position, Thesis } from '@/lib/types';

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

const marketThesis = thesis({
  id: 'MT1',
  name: 'Advanced Materials Growth',
  confidence: 0.8,
  horizon: 'long_term',
  notes: 'Materials demand is rising.',
  validation_criteria: ['Prices firm'],
  invalidation_criteria: ['Demand rolls over'],
});

const dashboardData = {
  portfolio: { strategy: { theses: [marketThesis] }, meta: { last_updated: '2026-07-17' } },
  positions: [position({ ticker: 'AAA', weight_actual: 20, thesis_ids: [] })],
} as unknown as DashboardData;

// `useDashboard` is a context hook this page reads directly (no parent shell
// wires props in, unlike `ThesesTab`) — mock it so the page renders standalone.
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ data: dashboardData, loading: false, error: null }),
}));

import ThesisDetailPageInner from './ThesisDetailPageInner';

describe('ThesisDetailPageInner (#1615 — bordered command + two-column dossier)', () => {
  it('renders a bordered command/identity band with thesis name, conviction, horizon, status, as-of', () => {
    const html = renderToStaticMarkup(createElement(ThesisDetailPageInner, { thesisId: 'MT1' }));
    expect(html).toContain('Advanced Materials Growth');
    expect(html).toContain('80% confidence');
    expect(html).toContain('long_term');
    expect(html).toContain('as of');
    expect(html).toContain('data-testid="thesis-command-band"');
  });

  it('uses a two-column dossier layout: narrative/criteria as main, vehicles/provenance as context', () => {
    const html = renderToStaticMarkup(createElement(ThesisDetailPageInner, { thesisId: 'MT1' }));
    expect(html).toContain('data-region="thesis-dossier"');
    expect(html).toContain('lg:grid-cols-[minmax(0,1fr)_minmax(18rem,0.7fr)]');
    expect(html).toContain('Materials demand is rising'); // narrative
    expect(html).toContain('What confirms this'); // criteria
  });

  it('renders the thesis statement (notes) in the main column', () => {
    const html = renderToStaticMarkup(createElement(ThesisDetailPageInner, { thesisId: 'MT1' }));
    expect(html).toContain('Materials demand is rising');
  });

  it('renders criteria columns in the main argument column', () => {
    const html = renderToStaticMarkup(createElement(ThesisDetailPageInner, { thesisId: 'MT1' }));
    expect(html).toContain('What confirms this');
    expect(html).toContain('Prices firm');
    expect(html).toContain('What breaks this');
    expect(html).toContain('Demand rolls over');
  });

  it('renders vehicle expressions in the context column', () => {
    const html = renderToStaticMarkup(createElement(ThesisDetailPageInner, { thesisId: 'MT1' }));
    expect(html).toContain('Vehicles expressing this view');
  });

  it('still renders the _unlinked branch via the honest holdings list', () => {
    const html = renderToStaticMarkup(
      createElement(ThesisDetailPageInner, { thesisId: '_unlinked' })
    );
    expect(html).toContain('Unlinked expressions');
    expect(html).toContain('Holdings expressing this thesis');
    expect(html).toContain('AAA');
  });

  it('renders the not-found state for an unknown thesis id', () => {
    const html = renderToStaticMarkup(createElement(ThesisDetailPageInner, { thesisId: 'ghost' }));
    expect(html).toContain('a thesis on record for');
  });
});
