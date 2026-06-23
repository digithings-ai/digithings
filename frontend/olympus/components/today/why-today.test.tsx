import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { WhyToday } from './why-today';

describe('WhyToday', () => {
  it('summarizes the day’s debates and links to the full reasoning', () => {
    const html = renderToStaticMarkup(
      createElement(WhyToday, {
        deliberations: [
          { ticker: 'NVDA', payload: { net_stance: 'bearish', conviction_delta: -3 } },
          { ticker: 'GLD', payload: { net_stance: 'bullish', conviction_delta: 2 } },
        ],
        pmMemoSummary: 'Reducing beta into a stretched tape; GLD as ballast.',
      })
    );
    expect(html).toContain('NVDA');
    expect(html).toContain('bearish');
    expect(html).toContain('Reducing beta into a stretched tape');
    expect(html).toContain('full debate');
  });

  it('renders nothing when there is neither a debate nor a memo', () => {
    const html = renderToStaticMarkup(
      createElement(WhyToday, { deliberations: [], pmMemoSummary: null })
    );
    expect(html).toBe('');
  });
});
