import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { TodaySummaries } from './today-summaries';
import type { Position } from '@/lib/types';

const pos = (ticker: string, weight_actual: number, weight_delta?: number): Position => ({
  ticker, name: ticker, type: 'LONG', weight_actual, weight_delta,
  current_price: null, entry_price: null, entry_date: null,
  rationale: '', thesis_ids: [], category: 'equity', pm_notes: '', stats: {},
});

describe('TodaySummaries', () => {
  it('renders the three quiet doorway cards with their content', () => {
    const html = renderToStaticMarkup(
      createElement(TodaySummaries, {
        positions: [pos('NVDA', 6.1, -2)],
        investedPct: null,
        theses: [{ id: 'T1', name: 'AI capex supercycle', status: 'confirmed' }],
        readSummary: 'Risk-off consolidation; rotating into defensives.',
        asOfDate: '2026-06-24',
      })
    );
    expect(html).toContain('The read');
    expect(html).toContain('Holdings');
    expect(html).toContain('Theses');
    expect(html).toContain('NVDA');
    expect(html).toContain('AI capex supercycle');
    expect(html).toContain('Risk-off consolidation');
    expect(html).not.toContain("How I'"); // performance doorway retired
  });

  it('shows holdings on the % of NAV basis (matches the book strip / portfolio table)', () => {
    // Live shape: holdings are % of NAV summing to invested_pct (90) with a CASH
    // row for the rest. scale → 1, so UUP reads its true 40.0% (not the old 36%),
    // and CASH never appears as a holding row (#1553).
    const html = renderToStaticMarkup(
      createElement(TodaySummaries, {
        positions: [pos('UUP', 40), pos('TLT', 35), pos('IJR', 15), pos('CASH', 10)],
        investedPct: 90,
        theses: [],
        readSummary: null,
        asOfDate: '2026-07-16',
      })
    );
    expect(html).toContain('UUP');
    expect(html).toContain('40.0%');
    expect(html).not.toContain('CASH');
  });

  it('handles an empty book without crashing', () => {
    const html = renderToStaticMarkup(
      createElement(TodaySummaries, {
        positions: [], investedPct: null, theses: [], readSummary: null, asOfDate: null,
      })
    );
    expect(html).toContain('Holdings');
    expect(html).toContain('Theses');
  });
});
