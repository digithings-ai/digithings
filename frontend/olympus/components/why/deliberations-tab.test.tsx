import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { DeliberationsPanel, sortDocsByDateDesc } from './deliberations-tab';
import type { PipelineTickerDoc } from '@/lib/types';

describe('DeliberationsPanel', () => {
  it('renders a ticker debate with its net stance', () => {
    const docs: PipelineTickerDoc[] = [
      {
        document_key: 'deliberation/NVDA',
        ticker: 'NVDA',
        payload: {
          net_stance: 'bullish',
          bull_thesis: 'Datacenter capex compounding.',
          bear_thesis: 'Valuation rich into earnings.',
          conviction_delta: '2',
        },
      },
    ];
    const html = renderToStaticMarkup(createElement(DeliberationsPanel, { docs }));
    expect(html).toContain('NVDA');
    expect(html).toContain('bullish');
    expect(html).toContain('Datacenter capex');
  });

  it('renders nothing when no payload is a debate summary', () => {
    const docs: PipelineTickerDoc[] = [{ document_key: 'x', ticker: 'X', payload: { foo: 'bar' } }];
    expect(renderToStaticMarkup(createElement(DeliberationsPanel, { docs }))).toBe('');
  });
});

describe('sortDocsByDateDesc', () => {
  it('sorts the most recent (today) above older docs', () => {
    const sorted = sortDocsByDateDesc([
      { id: 'a', date: '2026-06-10' },
      { id: 'b', date: '2026-06-22' },
      { id: 'c', date: '2026-06-15' },
    ]);
    expect(sorted.map((d) => d.id)).toEqual(['b', 'c', 'a']);
  });
});
