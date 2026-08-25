import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { href?: string; children?: unknown }) =>
    createElement('a', { href: p.href }, p.children),
}));

import PeriodInspectPanel from './PeriodInspectPanel';

describe('PeriodInspectPanel', () => {
  it('states the private accounting typed gap and does not invent rows', () => {
    const html = renderToStaticMarkup(createElement(PeriodInspectPanel));
    expect(html).toContain('data-testid="period-inspect-panel"');
    expect(html).toContain('data-period-state="typed-gap-private-accounting"');
    expect(html).toContain('Typed gap — private accounting');
    expect(html).toContain('olympus_accounting_');
    expect(html).toContain('/portfolio/performance');
    expect(html).not.toContain('opening_equity');
  });
});
