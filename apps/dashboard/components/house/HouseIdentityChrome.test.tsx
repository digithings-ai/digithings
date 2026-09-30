import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { href?: string; children?: import('react').ReactNode; className?: string }) =>
    createElement('a', { href: p.href, className: p.className }, p.children),
}));

import HouseIdentityChrome from './HouseIdentityChrome';

describe('HouseIdentityChrome', () => {
  it('renders Corpus | Book | Profile labels and house identity', () => {
    const html = renderToStaticMarkup(createElement(HouseIdentityChrome, { active: 'corpus' }));
    expect(html).toContain('data-testid="house-identity-chrome"');
    expect(html).toContain('Corpus');
    expect(html).toContain('Book');
    expect(html).toContain('Profile');
    expect(html).toContain('House ETF paper book');
    expect(html).toContain('/house?tab=book');
    expect(html).not.toContain('house-freshness');
  });

  it('shows freshness tone and run type when provided', () => {
    const html = renderToStaticMarkup(
      createElement(HouseIdentityChrome, {
        active: 'book',
        freshness: { tone: 'warn', label: 'Stale: last run 2026-09-01' },
        runType: 'delta',
      })
    );
    expect(html).toContain('data-testid="house-freshness"');
    expect(html).toContain('data-tone="warn"');
    expect(html).toContain('Stale: last run 2026-09-01');
    expect(html).toContain('delta');
  });
});
