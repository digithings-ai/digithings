/**
 * @vitest-environment happy-dom
 */
import { act, createElement, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const route = vi.hoisted(() => ({
  pathname: '/',
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: () => {}, replace: route.replace }),
}));

vi.mock('next/link', () => ({
  default: ({ href, children }: { href: string; children?: ReactNode }) =>
    createElement('a', { href }, children),
}));

vi.mock('@/components/app-shell-context', () => ({
  useAppShell: () => ({
    sidebarCollapsed: false,
    toggleSidebar: () => {},
    openCommandPalette: () => {},
    mobileNavOpen: false,
    setMobileNavOpen: () => {},
  }),
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ authEnabled: false, user: null, signOut: async () => {} }),
}));

vi.mock('@/lib/fx-hub-only', () => ({
  useFxHubOnlyInvitee: () => ({ canFxHub: true, fxHubOnlyInvitee: false }),
}));

vi.mock('@/components/sidebar-settings', () => ({ default: () => null }));
vi.mock('@/components/digichat-popup', () => ({
  default: () => createElement('div', { 'data-digichat-popup': '1' }),
}));

import DeskShell from '@/components/desk/shell/DeskShell';
import type { DeskPaneSlot } from '@/components/desk/shell/PaneGrid';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const panes: DeskPaneSlot[] = [
  {
    id: 'alpha',
    title: 'Alpha',
    chromePath: '/house/brief',
    eyebrow: '01',
    state: 'ready',
    columns: 6,
    children: 'alpha body',
  },
  {
    id: 'beta',
    title: 'Beta',
    chromePath: '/house/brief',
    eyebrow: '02',
    state: 'ready',
    columns: 6,
    children: 'beta body',
  },
];

describe('desk pane scaffolding', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    route.replace.mockClear();
    route.pathname = '/';
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    document.documentElement.style.overflow = '';
    document.body.style.overflow = '';
    window.sessionStorage.clear();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('returns from fullscreen on Escape without changing the route', () => {
    act(() => {
      root.render(createElement(DeskShell, { panes, children: null }));
    });
    const button = container.querySelector(
      '[aria-label="Fullscreen Alpha"]',
    ) as HTMLButtonElement;
    act(() => {
      button.click();
    });
    expect(container.querySelector('[data-pane-id="alpha"]')?.getAttribute('data-pane-fullscreen')).toBe(
      'true',
    );
    expect(container.querySelector('[data-pane-id="beta"]')).toBeNull();

    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(container.querySelector('[data-pane-id="alpha"]')?.getAttribute('data-pane-fullscreen')).toBe(
      'false',
    );
    expect(container.querySelector('[data-pane-id="beta"]')).not.toBeNull();
    expect(route.replace).not.toHaveBeenCalled();
    expect(route.pathname).toBe('/');
  });

  it('reorders panes and locks document scroll at desktop widths', () => {
    for (const width of [1280, 1920]) {
      Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
      act(() => {
        root.render(createElement(DeskShell, { panes, children: null }));
      });
      expect(document.documentElement.style.overflow).toBe('hidden');
      expect(window.innerWidth).toBe(width);
      const scrolling = document.scrollingElement;
      if (scrolling) scrolling.scrollTop = 80;
      act(() => {
        document.dispatchEvent(new Event('wheel', { bubbles: true, cancelable: true }));
      });
      expect(scrolling?.scrollTop).toBe(0);
    }

    const ids = () =>
      [...container.querySelectorAll('[data-pane-id]')].map((node) => node.getAttribute('data-pane-id'));
    expect(ids()).toEqual(['alpha', 'beta']);
    const later = container.querySelector('[aria-label="Move Alpha later"]') as HTMLButtonElement;
    act(() => {
      later.click();
    });
    expect(ids()).toEqual(['beta', 'alpha']);

    const narrowBeta = container.querySelector('[aria-label="Narrow Beta"]') as HTMLButtonElement;
    expect(narrowBeta).not.toBeNull();
    act(() => {
      narrowBeta.click();
    });
    const beta = container.querySelector('[data-pane-id="beta"]') as HTMLElement;
    expect(beta.getAttribute('style') ?? '').toContain('span 5');
    expect(container.querySelector('[data-chat-rail]')).not.toBeNull();
    expect(container.querySelector('[data-desk-rail]')).not.toBeNull();
  });
});
