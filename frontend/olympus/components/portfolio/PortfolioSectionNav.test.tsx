import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (p: { children?: unknown }) => p.children }));

import PortfolioSectionNav from './PortfolioSectionNav';

describe('PortfolioSectionNav', () => {
  it('shows the four book sections', () => {
    const html = renderToStaticMarkup(createElement(PortfolioSectionNav, { active: 'holdings' as const }));
    for (const label of ['Holdings', 'Theses', 'Performance', 'Attribution']) {
      expect(html).toContain(label);
    }
  });

  it('drops the legacy Allocations / Activity / Intelligence sections', () => {
    const html = renderToStaticMarkup(createElement(PortfolioSectionNav, { active: 'holdings' as const }));
    expect(html).not.toContain('Allocations');
    expect(html).not.toContain('Activity');
    expect(html).not.toContain('Intelligence');
  });
});
