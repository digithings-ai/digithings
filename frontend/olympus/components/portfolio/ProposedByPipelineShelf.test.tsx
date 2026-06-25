import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import ProposedByPipelineShelf from './ProposedByPipelineShelf';
import type { ProposedDecision } from '@/lib/holdings-decisions';

const p = (over: Partial<ProposedDecision>): ProposedDecision => ({
  ticker: 'IWM', conviction: 2, stance: 'buy', runDate: '2026-06-23', node: 'analyst/IWM', ...over,
});

describe('ProposedByPipelineShelf', () => {
  it('lists not-held decision tickers with a deep-link', () => {
    const html = renderToStaticMarkup(createElement(ProposedByPipelineShelf, {
      proposed: [p({}), p({ ticker: 'QQQ', node: 'analyst/QQQ' })],
    }));
    expect(html).toContain('Proposed by the pipeline');
    expect(html).toContain('IWM');
    expect(html).toContain('QQQ');
    expect(html).toContain('/pipeline?');
  });

  it('renders nothing when there is nothing proposed', () => {
    const html = renderToStaticMarkup(createElement(ProposedByPipelineShelf, { proposed: [] }));
    expect(html).toBe('');
  });
});
