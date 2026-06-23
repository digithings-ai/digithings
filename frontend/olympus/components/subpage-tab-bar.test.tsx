import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/olympus/twelve-x',
}));

import { SubpageStickyTabBar, subpageTabsContainerClass } from './subpage-tab-bar';

describe('subpageTabsContainerClass', () => {
  it('is visible (flex, not hidden) when open', () => {
    const cls = subpageTabsContainerClass(true);
    expect(cls).toContain('flex');
    expect(cls).not.toContain('hidden');
  });

  it('is hidden when closed', () => {
    expect(subpageTabsContainerClass(false)).toContain('hidden');
  });

  it('always shows tabs at >= md regardless of open', () => {
    expect(subpageTabsContainerClass(true)).toContain('md:flex');
    expect(subpageTabsContainerClass(false)).toContain('md:flex');
  });

  it('gates the dropdown-panel chrome behind max-md so it stops at md', () => {
    const cls = subpageTabsContainerClass(false);
    expect(cls).toContain('max-md:absolute');
    expect(cls).toContain('max-md:flex-col');
    // panel chrome must not leak to desktop (no unprefixed absolute/border/shadow)
    expect(cls).not.toMatch(/(^| )absolute( |$)/);
  });
});
