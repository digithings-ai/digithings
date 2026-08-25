import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { children?: unknown; href?: string }) =>
    createElement('a', { href: p.href }, p.children as never),
}));

import CorpusSectionNav from './CorpusSectionNav';

describe('CorpusSectionNav', () => {
  it('exposes Corpus | Book | Profile chrome', () => {
    const html = renderToStaticMarkup(createElement(CorpusSectionNav, { active: 'corpus' }));
    for (const label of ['Corpus', 'Book', 'Profile']) {
      expect(html).toContain(label);
    }
    expect(html).toContain('href="/corpus"');
    expect(html).toContain('href="/corpus?tab=book"');
    expect(html).toContain('href="/corpus?tab=profile"');
  });
});
