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
  decisions: [{ ticker: 'IWM', run_date: '2026-06-23', stance: 'buy', conviction: 2, status: 'pending' } as unknown as TableRow<'decision_log'>],
  positionHistory: [], thesisById: new Map<string, Thesis>(),
  effHistoryDate: '2026-06-23', onSelectHistoryDate: () => {}, onClearHistoryDate: () => {},
  showHistoryDateBanner: false, dateParam: null, historyMode: 'ticker' as const,
  setHistoryMode: () => {}, sleeveData: [], sleeveKeys: [], formatSleeveKey: (k: string) => k,
};

describe('AllocationsTab', () => {
  it('derives exposure from the displayed position book, not stale metrics', () => {
    const html = renderToStaticMarkup(createElement(AllocationsTab, base));
    expect(html).toContain('Invested');
    expect(html).toContain('60.0%');
    expect(html).not.toContain('75.0%');
    // Cash is intentionally shown in the slim summary; assert the derived split.
    expect(html).toContain('Cash');
    expect(html).toContain('40.0%');
  });

  it('keeps proposed unheld tickers in Pipeline rather than Holdings', () => {
    const html = renderToStaticMarkup(createElement(AllocationsTab, base));
    expect(html).not.toContain('Proposed by the pipeline');
    expect(html).not.toContain('IWM');
  });

  it('uses a full-width ledger with positions only', () => {
    const html = renderToStaticMarkup(createElement(AllocationsTab, base));
    expect(html).toContain('data-region="workspace"');
    expect(html).toContain('data-region="ledger"');
    expect(html).not.toContain('data-region="context-rail"');
    expect(html).not.toContain('Holdings view');
    expect(html).not.toContain('book monitor');
  });

  it('fills the available page height while keeping a minimum workspace height', () => {
    const html = renderToStaticMarkup(createElement(AllocationsTab, base));
    expect(html).toContain(
      'data-region="holdings-frame" class="flex min-h-[28rem] flex-1 flex-col overflow-hidden"',
    );
  });

  it('passes position count to the command band', () => {
    const html = renderToStaticMarkup(createElement(AllocationsTab, base));
    expect(html).toContain('Positions');
    expect(html).toContain('>2<'); // two positions in base fixture
  });

  it('prefers authoritative investedPct when provided (same SSOT as Brief)', () => {
    const html = renderToStaticMarkup(
      createElement(AllocationsTab, { ...base, investedPct: 55 })
    );
    expect(html).toContain('55.0%');
    expect(html).toContain('45.0%'); // cash = 100 − invested
    expect(html).not.toContain('60.0%');
  });
});
