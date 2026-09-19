import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import DivergenceChip from './DivergenceChip';

describe('DivergenceChip', () => {
  it('renders the gap label', () => {
    const html = renderToStaticMarkup(createElement(DivergenceChip, { gap: 1.75 }));
    expect(html).toContain('Δ1.75');
    expect(html).toContain('data-divergence-chip="true"');
  });

  it('calls onClick when provided', () => {
    const onClick = vi.fn();
    const html = renderToStaticMarkup(createElement(DivergenceChip, { gap: 1.2, onClick }));
    expect(html).toContain('type="button"');
  });
});
