import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';

import PipelineSummaryStrip from './PipelineSummaryStrip';
import type { RegimeChip } from './PipelineSummaryStrip';

const chips: RegimeChip[] = [
  { label: 'Growth', value: 'slowing', color: 'amber' },
  { label: 'Inflation', value: 'cooling', color: 'green' },
];

describe('PipelineSummaryStrip', () => {
  it('renders the headline text', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineSummaryStrip, {
        headline: 'Mixed signals across asset classes',
        regimeChips: chips,
        decision: '4 holdings · 75% invested',
      }),
    );
    expect(html).toContain('Mixed signals across asset classes');
  });

  it('renders regime chips', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineSummaryStrip, {
        headline: 'Test headline',
        regimeChips: chips,
        decision: null,
      }),
    );
    expect(html).toContain('Growth');
    expect(html).toContain('slowing');
    expect(html).toContain('Inflation');
  });

  it('renders the decision chip when provided', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineSummaryStrip, {
        headline: 'Test',
        regimeChips: [],
        decision: '4 holdings · 75% invested',
      }),
    );
    expect(html).toContain('4 holdings');
  });

  it('uses warn for amber chips (not up/down for non-financial values)', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineSummaryStrip, {
        headline: 'Test',
        regimeChips: [{ label: 'Growth', value: 'slowing', color: 'amber' }],
        decision: null,
      }),
    );
    // amber chip should use warn token, not up or down
    expect(html).toContain('warn');
    expect(html).not.toContain('fin-purple');
  });

  it('does not use P&L colors for directional regime chips', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineSummaryStrip, {
        headline: 'Test',
        regimeChips: [
          { label: 'Inflation', value: 'cooling', color: 'green' },
          { label: 'Growth', value: 'contracting', color: 'red' },
        ],
        decision: null,
      }),
    );
    expect(html).not.toContain('bg-up');
    expect(html).not.toContain('bg-down');
  });
});
