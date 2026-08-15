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
  it('is always a visible flex row — the mobile dropdown is gone (#1570)', () => {
    const cls = subpageTabsContainerClass();
    expect(cls.split(' ')).toContain('flex');
    expect(cls).not.toContain('hidden');
  });

  it('mobile is a nowrap scroll row; desktop wraps in place', () => {
    const cls = subpageTabsContainerClass();
    expect(cls).toContain('max-md:flex-nowrap');
    expect(cls).toContain('max-md:overflow-x-auto');
    expect(cls).toContain('subnav-scroll');
    expect(cls).toContain('md:flex-wrap');
  });

  it('carries no dropdown-panel chrome (no absolute positioning at any width)', () => {
    const cls = subpageTabsContainerClass();
    expect(cls).not.toContain('absolute');
    expect(cls).not.toContain('max-md:flex-col');
  });
});

describe('subpageTabButtonClass', () => {
  it('chips never shrink — required for the mobile scroll row', () => {
    expect(subpageTabButtonClass(true)).toContain('shrink-0');
    expect(subpageTabButtonClass(false)).toContain('shrink-0');
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

  it('renders NO mobile menu trigger — sections are a scroll row, not a dropdown (#1570)', () => {
    const html = renderBar();
    expect(html).not.toContain('aria-expanded');
    expect(html).not.toContain('Sections');
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

  it('tabs are always rendered (no hidden state)', () => {
    const container = renderBar().match(/id="subpage-tabs"[^>]*class="([^"]*)"/)?.[1] ?? '';
    expect(container.split(' ')).toContain('flex');
    expect(container.split(' ')).not.toContain('hidden');
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
    expect(renderButtonBar()).not.toContain('-panel-');
  });

  it('desktop strip hides below md; the children container becomes the mobile scroll row', () => {
    const html = renderButtonBar();
    expect(html).toContain('hidden md:block');
    const container = html.match(/id="subpage-tabs"[^>]*class="([^"]*)"/)?.[1] ?? '';
    expect(container.split(' ')).toContain('md:hidden');
    expect(container.split(' ')).toContain('max-md:overflow-x-auto');
    expect(container.split(' ')).not.toContain('md:flex');
  });

  it('still renders the raw children for the mobile row', () => {
    const html = renderButtonBar();
    // once in the TabStrip label, once in the mobile-row child
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
  });
});
