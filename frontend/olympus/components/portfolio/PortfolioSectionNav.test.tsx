import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { children?: unknown; href?: string }) =>
    createElement('a', { href: p.href }, p.children as never),
}));

import PortfolioSectionNav from './PortfolioSectionNav';

describe('PortfolioSectionNav', () => {
  it('shows Tearsheet | Ledger | Period inspect chrome with book sections', () => {
    const html = renderToStaticMarkup(createElement(PortfolioSectionNav, { active: 'holdings' }));
    for (const label of ['Holdings', 'Theses', 'Tearsheet', 'Ledger', 'Period', 'Attribution']) {
      expect(html).toContain(label);
    }
    expect(html).toContain('href="/portfolio/performance"');
    expect(html).toContain('href="/portfolio/ledger"');
    expect(html).toContain('href="/portfolio/period"');
  });

  it('drops the legacy Allocations / Activity / Intelligence / Performance labels', () => {
    const html = renderToStaticMarkup(createElement(PortfolioSectionNav, { active: 'holdings' }));
    expect(html).not.toContain('Allocations');
    expect(html).not.toContain('Activity');
    expect(html).not.toContain('Intelligence');
    expect(html).not.toContain('>Performance<');
  });
});
