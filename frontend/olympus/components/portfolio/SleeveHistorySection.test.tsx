import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import SleeveHistorySection from './SleeveHistorySection';

const base = {
  historyMode: 'ticker' as const, setHistoryMode: () => {}, sleeveKeys: ['NVDA'],
  formatSleeveKey: (k: string) => k, effHistoryDate: '2026-06-23',
  onSelectHistoryDate: () => {}, showHistoryDateBanner: false, dateParam: null,
  onClearHistoryDate: () => {},
};

describe('SleeveHistorySection', () => {
  it('collapses to an element-specific empty state on single-day data', () => {
    const html = renderToStaticMarkup(createElement(SleeveHistorySection, {
      ...base, sleeveData: [{ date: '2026-06-23', NVDA: 30 }],
    }));
    expect(html).toContain('Sleeve history builds daily');
    expect(html).not.toContain('Sleeve weights stacked over time');
  });

  it('renders the stacked chart when ≥2 dates exist', () => {
    const html = renderToStaticMarkup(createElement(SleeveHistorySection, {
      ...base, sleeveData: [{ date: '2026-06-23', NVDA: 30 }, { date: '2026-06-24', NVDA: 31 }],
    }));
    expect(html).toContain('Sleeve weights stacked over time');
  });
});
