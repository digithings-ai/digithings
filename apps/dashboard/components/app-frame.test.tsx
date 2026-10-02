import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

const route = vi.hoisted(() => ({
  pathname: '/portfolio',
  search: '',
}));

vi.mock('next/navigation', () => ({
  usePathname: () => route.pathname,
  useSearchParams: () => new URLSearchParams(route.search),
  useRouter: () => ({ push: () => {}, replace: () => {} }),
}));

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    ...rest
  }: {
    href: string;
    children?: ReactNode;
  }) => createElement('a', { href, ...rest }, children),
}));

vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({
    dbStatus: 'ok',
    data: null,
    api: null,
    loading: false,
    error: null,
  }),
}));

vi.mock('@/components/sidebar', () => ({
  default: () => createElement('aside', { 'data-sidebar': 'legacy' }),
}));

vi.mock('@/components/mobile-app-bar', () => ({ default: () => null }));

vi.mock('@/components/command-palette', () => ({ default: () => null }));

vi.mock('@/components/fx-hub-only-guard', () => ({
  default: ({ children }: { children?: ReactNode }) => children ?? null,
}));

vi.mock('@/components/db-unavailable', () => ({ default: () => null }));

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
vi.mock('@/components/digichat-popup', () => ({ default: () => null }));

import AppFrame from './app-frame';
import { DeskPicker } from '@/components/desk/shell/DeskPicker';

describe('AppFrame desk shell flag', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    route.pathname = '/portfolio';
    route.search = '';
  });

  it('keeps the scrolling shell when the flag is off', () => {
    vi.stubEnv('NEXT_PUBLIC_DESK_SHELL', '');
    const html = renderToStaticMarkup(createElement(AppFrame, null, 'brief body'));
    expect(html).toContain('overflow-y-auto');
    expect(html).toContain('data-sidebar="legacy"');
    expect(html).not.toContain('data-desk-shell');
    expect(html).toContain('brief body');
  });

  it('mounts one viewport, the holdings path, the rail, and the chat column when the flag is on', () => {
    vi.stubEnv('NEXT_PUBLIC_DESK_SHELL', '1');
    const html = renderToStaticMarkup(createElement(AppFrame, null, 'brief body'));
    expect(html).toContain('data-desk-shell');
    expect(html).toContain('data-document-scroll="locked"');
    expect(html).toContain('h-dvh');
    expect(html).toContain('overflow-hidden');
    expect(html).toContain('house / portfolio / holdings');
    expect(html).toContain('>holdings<');
    expect(html).toContain('data-chat-rail');
    expect(html).toContain('data-desk-rail');
    expect(html).not.toContain('Corpus');
    expect(html).not.toContain('Profile');
    expect(html).toContain('brief body');
    expect(html).toContain('paper / research');
  });

  it('shows an honest rates-watch banner instead of a blank page', () => {
    vi.stubEnv('NEXT_PUBLIC_DESK_SHELL', '1');
    route.pathname = '/';
    route.search = 'desk=rates-watch&section=watchlist';
    const html = renderToStaticMarkup(createElement(AppFrame, null, 'should not show'));
    expect(html).toContain('rates watch / watchlist');
    expect(html).toContain('not a second book');
    expect(html).toContain('[wip]');
    expect(html).not.toContain('should not show');
  });
});

describe('DeskPicker', () => {
  it('lists house, rates watch, and FX Hub in the popover and the fullscreen menu', () => {
    const popover = renderToStaticMarkup(
      createElement(DeskPicker, { deskId: 'house', initialMenu: 'popover' }),
    );
    expect(popover).toContain('data-desk-picker-menu="popover"');
    expect(popover).toContain('w-80');
    expect(popover).toContain('>house<');
    expect(popover).toContain('rates watch');
    expect(popover).toContain('FX Hub');
    expect(popover).toContain('[wip]');

    const fullscreen = renderToStaticMarkup(
      createElement(DeskPicker, { deskId: 'house', initialMenu: 'fullscreen' }),
    );
    expect(fullscreen).toContain('data-desk-picker-menu="fullscreen"');
    expect(fullscreen).toContain('rates watch');
  });
});
