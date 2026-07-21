import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/why',
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('why=read'),
}));

vi.mock('@/components/why/the-read', () => ({
  TheRead: () => createElement('div', { 'data-testid': 'read-content' }, 'read'),
}));

vi.mock('@/components/why/deliberations-tab', () => ({
  DeliberationsTab: () => createElement('div', { 'data-testid': 'deliberations-content' }, 'deliberations'),
}));

import WhyClient from './why-client';

describe('WhyClient', () => {
  it('renders one reasoning command band before the active view', () => {
    const html = renderToStaticMarkup(createElement(WhyClient));
    expect(html).toContain('data-testid="why-workspace"');
    expect(html).toContain('data-testid="why-command-band"');
    expect(html).toContain('Why the book looks this way');
    expect(html.indexOf('why-command-band')).toBeLessThan(html.indexOf('read-content'));
    expect(html).toContain('lg:grid-cols-[minmax(0,1fr)_auto]');
    expect(html).not.toContain('md:grid-cols-[minmax(0,1fr)_auto]');
    expect(html).not.toContain('glass-card');
  });
});