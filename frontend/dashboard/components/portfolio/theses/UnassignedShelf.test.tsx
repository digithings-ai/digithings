import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { UnassignedShelf } from './UnassignedShelf';
import type { Position } from '@/lib/types';

vi.mock('next/link', () => ({
  default: ({ children, href, className }: { children?: unknown; href?: string; className?: string }) =>
    createElement('a', { href, className }, children),
}));

const held = [
  {
    ticker: 'TLT',
    name: 'Long Treasuries',
    type: 'LONG',
    weight_actual: 8.5,
    current_price: null,
    entry_price: null,
    entry_date: null,
    rationale: '',
    thesis_ids: [],
    category: 'bond',
    pm_notes: '',
    stats: {},
  },
] as Position[];

describe('UnassignedShelf tier gate', () => {
  it('locks held weight list for Observer', () => {
    const html = renderToStaticMarkup(
      createElement(UnassignedShelf, {
        heldUnmapped: held,
        proposedUnheld: [],
        tier: 'free',
      }),
    );
    expect(html).toContain('locked-surface');
    expect(html).not.toContain('8.5%');
  });

  it('passthrough weights for Brief', () => {
    const html = renderToStaticMarkup(
      createElement(UnassignedShelf, {
        heldUnmapped: held,
        proposedUnheld: [],
        tier: 'brief',
      }),
    );
    expect(html).toContain('TLT');
    expect(html).toContain('8.5%');
    expect(html).not.toContain('locked-surface');
  });
});
