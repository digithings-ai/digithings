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
    expect(cls.split(' ')).toContain('flex');
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

function renderBar(): string {
  return renderToStaticMarkup(
    createElement(
      SubpageStickyTabBar,
      { 'aria-label': 'Test sections' },
      createElement('a', { href: '/a', key: 'a' }, 'Alpha'),
      createElement('a', { href: '/b', key: 'b' }, 'Bravo'),
    ),
  );
}

describe('SubpageStickyTabBar', () => {
  it('renders its tab children', () => {
    const html = renderBar();
    expect(html).toContain('Alpha');
    expect(html).toContain('Bravo');
  });

  it('renders a collapsed mobile menu trigger', () => {
    const html = renderBar();
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-controls="subpage-tabs"');
    expect(html).toContain('Sections');
    // Trigger must be hidden on desktop so the desktop layout is not broken.
    expect(html).toContain('md:hidden');
  });

  it('outer wrapper is full-bleed: has the border, sticky, but no width cap', () => {
    const html = renderBar();
    const firstClass = html.match(/class="([^"]*)"/)?.[1] ?? '';
    expect(firstClass).toContain('sticky');
    expect(firstClass).toContain('border-b');
    expect(firstClass).not.toContain('max-w-[1600px]');
  });

  it('inner wrapper caps content at 1600px', () => {
    expect(renderBar()).toContain('max-w-[1600px]');
  });

  it('respects a custom menuLabel', () => {
    const html = renderToStaticMarkup(
      createElement(SubpageStickyTabBar, { menuLabel: 'Views' }, createElement('a', { href: '/a' }, 'A')),
    );
    expect(html).toContain('Views');
  });

  it('tabs container has hidden and md:flex classes in default (closed) state', () => {
    const html = renderBar();
    expect(html).toContain('hidden');
    expect(html).toContain('md:flex');
  });
});
