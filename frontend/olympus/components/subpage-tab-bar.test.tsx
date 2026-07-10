import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/olympus/twelve-x',
}));

import {
  SubpageStickyTabBar,
  subpageTabButtonClass,
  subpageTabsContainerClass,
} from './subpage-tab-bar';

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

  it('link tabs keep the plain desktop row — no ARIA tablist', () => {
    // Route navigation is nav-link semantics (cmd-click, prefetch), not tabs.
    expect(renderBar()).not.toContain('role="tablist"');
  });
});

function renderButtonBar(): string {
  return renderToStaticMarkup(
    createElement(
      SubpageStickyTabBar,
      { 'aria-label': 'Panel sections' },
      createElement(
        'button',
        { type: 'button', key: 'a', className: subpageTabButtonClass(true) },
        'Alpha',
      ),
      createElement(
        'button',
        { type: 'button', key: 'b', className: subpageTabButtonClass(false) },
        'Bravo',
      ),
    ),
  );
}

describe('SubpageStickyTabBar — TabStrip-backed desktop row (button tabs)', () => {
  it('renders the shared TabStrip as an ARIA tablist in the chip dress', () => {
    const html = renderButtonBar();
    expect(html).toContain('role="tablist"');
    expect(html).toContain('tab-strip chip');
    expect(html).toContain('tab-ink chip');
  });

  it('marks the active tab with aria-selected and a roving tabindex', () => {
    const html = renderButtonBar();
    expect(html.match(/aria-selected="true"/g)).toHaveLength(1);
    expect(html.match(/aria-selected="false"/g)).toHaveLength(1);
    expect(html.match(/role="tab"[^>]*tabindex="0"/g)).toHaveLength(1);
    expect(html.match(/role="tab"[^>]*tabindex="-1"/g)).toHaveLength(1);
  });

  it('omits aria-controls — the legacy children own no panel ids', () => {
    // The mobile trigger's aria-controls="subpage-tabs" is the only one.
    expect(renderButtonBar()).not.toContain('-panel-');
  });

  it('desktop strip hides below md; the children container becomes mobile-only', () => {
    const html = renderButtonBar();
    expect(html).toContain('hidden md:block');
    const container = html.match(/id="subpage-tabs"[^>]*class="([^"]*)"/)?.[1] ?? '';
    expect(container.split(' ')).toContain('md:hidden');
    expect(container.split(' ')).not.toContain('md:flex');
  });

  it('still renders the raw children for the mobile dropdown', () => {
    const html = renderButtonBar();
    // once in the TabStrip label, once in the dropdown child
    expect(html.match(/Alpha/g)).toHaveLength(2);
    expect(html.match(/Bravo/g)).toHaveLength(2);
  });

  it('falls back to the plain row when no child is active', () => {
    const html = renderToStaticMarkup(
      createElement(
        SubpageStickyTabBar,
        {},
        createElement(
          'button',
          { type: 'button', key: 'a', className: subpageTabButtonClass(false) },
          'A',
        ),
      ),
    );
    expect(html).not.toContain('role="tablist"');
    expect(html).toContain('md:flex');
  });
});
