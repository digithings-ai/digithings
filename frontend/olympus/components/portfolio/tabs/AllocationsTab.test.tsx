import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import AllocationsTab from './AllocationsTab';
import type { Position, Thesis } from '@/lib/types';
import type { TableRow } from '@/lib/database.types';

const position = (over: Partial<Position>): Position => ({
  ticker: 'NVDA', name: 'NVIDIA', type: 'LONG', weight_actual: 30, weight_target: null,
  weight_delta: null, current_price: 100, entry_price: 90, entry_date: null, rationale: '',
  thesis_ids: [], category: 'equity', pm_notes: '', stats: {}, conviction: 3,
  sector_bucket: 'Technology', ...over,
});

const base = {
  lastUpdated: '2026-06-23',
  positions: [position({ ticker: 'NVDA' }), position({ ticker: 'EWT', sector_bucket: 'International' })],
  investedPct: 75,
  decisions: [{ ticker: 'IWM', run_date: '2026-06-23', stance: 'buy', conviction: 2, status: 'pending' } as unknown as TableRow<'decision_log'>],
  positionHistory: [], positionEvents: [], thesisById: new Map<string, Thesis>(),
  effHistoryDate: '2026-06-23', onSelectHistoryDate: () => {}, onClearHistoryDate: () => {},
  showHistoryDateBanner: false, dateParam: null, historyMode: 'ticker' as const,
  setHistoryMode: () => {}, sleeveData: [], sleeveKeys: [], formatSleeveKey: (k: string) => k,
};

describe('AllocationsTab', () => {
  it('renders the reconciliation strip with normalized invested/cash', () => {
    const html = renderToStaticMarkup(createElement(AllocationsTab, base));
    expect(html).toContain('Invested');
    expect(html).toContain('75.0%');
    expect(html).toContain('Cash');
  });

  it('renders the proposed-by-pipeline shelf for not-held decision tickers', () => {
    const html = renderToStaticMarkup(createElement(AllocationsTab, base));
    expect(html).toContain('Proposed by the pipeline');
    expect(html).toContain('IWM');
  });
});
