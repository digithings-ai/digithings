import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { TwelveXProvider, type TwelveXContextValue } from './context';
import BriefsIndex, { availableBriefRunDates, briefsForRunDate } from './BriefsIndex';

const ctx: TwelveXContextValue = {
  runDate: '2026-06-22',
  crossLink: () => {},
  openBrief: () => {},
  watchlist: {
    items: [],
    has: () => false,
    toggle: () => {},
    clear: () => {},
    filterOn: false,
    setFilterOn: () => {},
  },
};

function brief(partial: Partial<FxBriefRow> & Pick<FxBriefRow, 'run_date' | 'source_file' | 'document_title'>): FxBriefRow {
  return {
    source_url: null,
    broker_name: 'Desk',
    analyst_names: null,
    report_date: partial.run_date,
    trader_relevance: 'medium',
    central_thesis: 'Thesis',
    brief_markdown: null,
    currency_views: [],
    risk_events: [],
    macro_themes: [],
    positioning_signals: [],
    ...partial,
  };
}

const windowBriefs: FxBriefRow[] = [
  brief({
    run_date: '2026-06-22',
    source_file: 'a.md',
    document_title: 'Board 22 A',
    trader_relevance: 'high',
  }),
  brief({
    run_date: '2026-06-22',
    source_file: 'b.md',
    document_title: 'Board 22 B',
    trader_relevance: 'low',
  }),
  brief({
    run_date: '2026-06-20',
    source_file: 'c.md',
    document_title: 'Board 20 only',
    trader_relevance: 'medium',
  }),
];

describe('BriefsIndex helpers', () => {
  it('lists distinct run_dates newest-first', () => {
    expect(availableBriefRunDates(windowBriefs)).toEqual(['2026-06-22', '2026-06-20']);
  });

  it('filters and sorts briefs for a board date', () => {
    const day = briefsForRunDate(windowBriefs, '2026-06-22');
    expect(day.map((b) => b.document_title)).toEqual(['Board 22 A', 'Board 22 B']);
    expect(briefsForRunDate(windowBriefs, '2026-06-21')).toEqual([]);
  });
});

describe('BriefsIndex', () => {
  it('defaults to the canonical board date and exposes a date filter', () => {
    const html = renderToStaticMarkup(
      createElement(
        TwelveXProvider,
        { value: ctx },
        createElement(BriefsIndex, {
          briefs: windowBriefs,
          defaultDate: '2026-06-22',
          onBack: () => {},
        }),
      ),
    );
    expect(html).toContain('Broker briefs');
    expect(html).toContain('aria-label="Filter briefs by board date"');
    expect(html).toContain('value="2026-06-22"');
    expect(html).toContain('Board 22 A');
    expect(html).toContain('Board 22 B');
    expect(html).not.toContain('Board 20 only');
    expect(html).toContain('aria-label="Available board dates"');
  });
});
