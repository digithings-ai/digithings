import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { href?: string; children?: unknown; className?: string }) =>
    createElement('a', { href: p.href, className: p.className }, p.children),
}));

import HouseIdentityChrome from './HouseIdentityChrome';
import HouseIdentityBanner from './HouseIdentityBanner';

describe('HouseIdentityChrome', () => {
  it('renders Corpus | Book | Profile labels and house identity', () => {
    const html = renderToStaticMarkup(createElement(HouseIdentityChrome, { active: 'corpus' }));
    expect(html).toContain('data-testid="house-identity-chrome"');
    expect(html).toContain('Corpus');
    expect(html).toContain('Book');
    expect(html).toContain('Profile');
    expect(html).toContain('digithings');
    expect(html).toContain('House ETF paper book');
    expect(html).toContain('/house?tab=book');
  });
});

describe('HouseIdentityBanner', () => {
  it('links into Corpus Book Profile chrome', () => {
    const html = renderToStaticMarkup(createElement(HouseIdentityBanner));
    expect(html).toContain('data-testid="house-identity-banner"');
    expect(html).toContain('/house?tab=corpus');
    expect(html).toContain('Corpus · Book · Profile');
  });
});
