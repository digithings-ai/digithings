import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { ThesisHoldingsExpressing } from './ThesisHoldingsExpressing';
import type { Position } from '@/lib/types';

vi.mock('next/link', () => ({
  default: ({ children, href, className }: { children?: unknown; href?: string; className?: string }) =>
    createElement('a', { href, className }, children),
}));

const positions = [
  {
    ticker: 'NVDA',
    name: 'NVIDIA',
    type: 'LONG',
    weight_actual: 12.5,
    conviction: 3,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: '',
    thesis_ids: [],
    category: 'equity',
    pm_notes: '',
    stats: {},
  },
] as Position[];

describe('ThesisHoldingsExpressing tier gate', () => {
  it('locks weight list for Observer', () => {
    const html = renderToStaticMarkup(
      createElement(ThesisHoldingsExpressing, { positions, tier: 'free' }),
    );
    expect(html).toContain('Holdings expressing this thesis');
    expect(html).toContain('locked-surface');
    expect(html).not.toContain('12.5%');
    expect(html).not.toContain('NVDA');
  });

  it('passthrough weights for Baseline', () => {
    const html = renderToStaticMarkup(
      createElement(ThesisHoldingsExpressing, { positions, tier: 'baseline' }),
    );
    expect(html).toContain('NVDA');
    expect(html).toContain('12.5%');
    expect(html).not.toContain('locked-surface');
  });
});
