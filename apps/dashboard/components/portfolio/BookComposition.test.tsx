import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { ReconciledPosition } from '@/lib/book-reconciliation';
import type { PositionHistoryRow } from '@/lib/types';
import BookComposition, { type BookCompositionProps } from './BookComposition';

const live = (ticker: string, w: number) =>
  ({ ticker, category: 'equity', thesis_ids: [], normalizedWeight: w }) as unknown as ReconciledPosition;

const history: PositionHistoryRow[] = [
  { date: '2026-09-01', ticker: 'SPY', weight_pct: 60, category: 'equity', thesis_id: null },
  { date: '2026-09-29', ticker: 'NVDA', weight_pct: 40, category: 'equity', thesis_id: null },
];

const base: BookCompositionProps = {
  rows: [live('NVDA', 40), live('EWT', 35)],
  cashPct: 25,
  positionHistory: history,
  theses: [],
  mode: 'ticker',
  onModeChange: () => {},
  sleeveData: [
    { date: '2026-09-01', SPY: 60 },
    { date: '2026-09-29', NVDA: 40 },
  ],
  sleeveKeys: ['SPY', 'NVDA'],
  formatSleeveKey: (k) => k,
  effHistoryDate: '2026-09-29',
  dateParam: null,
  showHistoryDateBanner: false,
  onSelectHistoryDate: () => {},
  onClearHistoryDate: () => {},
};

const render = (over: Partial<BookCompositionProps> = {}) =>
  renderToStaticMarkup(createElement(BookComposition, { ...base, ...over }));

describe('BookComposition', () => {
  it('shows the live book by default, with no history banner', () => {
    const html = render();
    expect(html).toContain('Composition now');
    expect(html).not.toContain('data-testid="history-date-banner"');
    expect(html).toContain('NVDA 40%');
    expect(html).toContain('2 groups held.');
  });

  it('pins a stored date: heading, banner and that day’s book, not today’s', () => {
    const html = render({
      dateParam: '2026-09-01',
      effHistoryDate: '2026-09-01',
      showHistoryDateBanner: true,
    });
    expect(html).toContain('Composition on 2026-09-01');
    expect(html).toContain('data-testid="history-date-banner"');
    expect(html).toContain('Back to live book');
    expect(html).toContain('SPY 60%');
    expect(html).toContain('1 group held.');
  });

  it('offers the date pager only when there is more than one stored date', () => {
    expect(render()).toContain('Pick book date');
    expect(render({ sleeveData: [{ date: '2026-09-29', NVDA: 40 }] })).not.toContain(
      'Pick book date',
    );
  });
});
