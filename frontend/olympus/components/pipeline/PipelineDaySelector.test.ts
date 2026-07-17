import { describe, it, expect } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import PipelineDaySelector from './PipelineDaySelector';
import { adjacentDates } from './PipelineDaySelector';

/**
 * Regression for #1538 — the original index math assumed an ASCENDING date list
 * but PipelineClient passes dates newest-first, so "Previous day" (chevron-left)
 * navigated FORWARD in time and "Next day" navigated backward, and on the
 * newest date the only enabled arrow moved the wrong way.
 */
describe('adjacentDates (newest-first list)', () => {
  const dates = ['2026-07-16', '2026-07-15', '2026-07-14'];

  it('previous (chevron-left) is the chronologically OLDER date', () => {
    expect(adjacentDates(dates, '2026-07-15').prev).toBe('2026-07-14');
  });

  it('next (chevron-right) is the chronologically NEWER date', () => {
    expect(adjacentDates(dates, '2026-07-15').next).toBe('2026-07-16');
  });

  it('newest date: next disabled, previous still reaches yesterday', () => {
    const { prev, next } = adjacentDates(dates, '2026-07-16');
    expect(next).toBeNull();
    expect(prev).toBe('2026-07-15');
  });

  it('oldest date: previous disabled', () => {
    const { prev, next } = adjacentDates(dates, '2026-07-14');
    expect(prev).toBeNull();
    expect(next).toBe('2026-07-15');
  });

  it('value not in the list (e.g. UTC-today before the run): both disabled', () => {
    expect(adjacentDates(dates, '2026-07-17')).toEqual({ prev: null, next: null });
  });
});

describe('PipelineDaySelector', () => {
  it('presents the current run date as a labelled pager', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineDaySelector, {
        dates: ['2026-07-17', '2026-07-16'],
        value: '2026-07-17',
        onChange: () => {},
      }),
    );

    expect(html).toContain('Run date');
    expect(html).toContain('Fri, Jul 17, 2026');
    expect(html).toContain('Previous day');
    expect(html).toContain('Next day');
  });
});
