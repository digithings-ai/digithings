import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import ArchitecturePage from './page';

describe('ArchitecturePage', () => {
  it('renders the top-level title, clearer phase label, and path tokens', () => {
    const html = renderToStaticMarkup(createElement(ArchitecturePage));

    expect(html).toContain('<h1');
    expect(html).toContain('Atlas Architecture');
    expect(html).toContain('Agent Phase Map');
    expect(html).not.toContain('Phase Graph');
    expect(html).toContain('<code');
    expect(html).toContain('atlas/phases/phase1_altdata.py');
  });
});
