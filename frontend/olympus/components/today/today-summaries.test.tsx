import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { TodaySummaries } from './today-summaries';

describe('TodaySummaries', () => {
  it('renders the four quiet doorway cards with their content', () => {
    const html = renderToStaticMarkup(
      createElement(TodaySummaries, {
        navSpark: [100, 101], // < 3 → sparkline skipped, deterministic for SSR
        excessPct: 4.2,
        sharpe: 1.1,
        positions: [{ ticker: 'NVDA', name: 'NVIDIA', weight_actual: 6.1, weight_delta: -2 }],
        theses: [{ id: 'T1', name: 'AI capex supercycle', status: 'confirmed' }],
        readSummary: 'Risk-off consolidation; rotating into defensives.',
      })
    );
    // four section labels
    expect(html).toContain('How I'); // "How I'm doing" (apostrophe-agnostic)
    expect(html).toContain('The read');
    expect(html).toContain('Holdings');
    expect(html).toContain('Theses');
    // content from each card
    expect(html).toContain('+4.2%'); // excess
    expect(html).toContain('1.10'); // sharpe
    expect(html).toContain('NVDA');
    expect(html).toContain('AI capex supercycle');
    expect(html).toContain('Risk-off consolidation');
    // the performance doorway CTA
    expect(html).toContain('Performance');
  });

  it('handles an empty book without crashing', () => {
    const html = renderToStaticMarkup(
      createElement(TodaySummaries, {
        navSpark: [],
        excessPct: null,
        sharpe: null,
        positions: [],
        theses: [],
        readSummary: null,
      })
    );
    expect(html).toContain('Holdings');
    expect(html).toContain('Theses');
  });
});
