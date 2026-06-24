import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { TodaySummaries } from './today-summaries';

describe('TodaySummaries', () => {
  it('renders the three quiet doorway cards with their content', () => {
    const html = renderToStaticMarkup(
      createElement(TodaySummaries, {
        positions: [{ ticker: 'NVDA', name: 'NVIDIA', weight_actual: 6.1, weight_delta: -2 }],
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

  it('handles an empty book without crashing', () => {
    const html = renderToStaticMarkup(
      createElement(TodaySummaries, {
        positions: [], theses: [], readSummary: null, asOfDate: null,
      })
    );
    expect(html).toContain('Holdings');
    expect(html).toContain('Theses');
  });
});
