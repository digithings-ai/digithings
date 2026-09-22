import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, it, expect, vi } from 'vitest';

const navMock = vi.hoisted(() => ({ pathname: '/' as string }));
vi.mock('next/navigation', () => ({ usePathname: () => navMock.pathname }));

const dashMock = vi.hoisted(() => ({ dbStatus: 'ok' as 'ok' | 'unconfigured' | 'unreachable' }));
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ dbStatus: dashMock.dbStatus, data: null, loading: false, error: null }),
}));

const shellMock = vi.hoisted(() => ({ sidebarCollapsed: false }));
vi.mock('@/components/app-shell-context', () => ({
  useAppShell: () => ({
    sidebarCollapsed: shellMock.sidebarCollapsed,
    toggleSidebar: () => {},
    mobileNavOpen: false,
    setMobileNavOpen: () => {},
    toggleMobileNav: () => {},
    commandPaletteOpen: false,
    openCommandPalette: () => {},
    closeCommandPalette: () => {},
  }),
}));

// Leaf chrome: markers only, so the frame's own layout is what is asserted.
vi.mock('@/components/sidebar', () => ({ default: () => createElement('nav', { 'data-testid': 'sidebar' }) }));
vi.mock('@/components/mobile-app-bar', () => ({ default: () => null }));
vi.mock('@/components/command-palette', () => ({ default: () => null }));
vi.mock('@/components/digichat-popup', () => ({ default: () => null }));
vi.mock('@/components/fx-hub-only-guard', () => ({
  default: (p: { children?: unknown }) => createElement('div', { 'data-testid': 'guard' }, p.children),
}));
vi.mock('@/components/db-unavailable', () => ({
  default: ({ status }: { status: string }) =>
    createElement('div', { 'data-testid': 'db-unavailable', 'data-status': status }),
}));

import AppFrame from './app-frame';

function render() {
  return renderToStaticMarkup(createElement(AppFrame, null, createElement('p', null, 'PAGE')));
}

function mainClass(html: string): string {
  return html.match(/<main[^>]*class="([^"]*)"/)?.[1] ?? '';
}

describe('AppFrame — explicit layout', () => {
  beforeEach(() => {
    navMock.pathname = '/';
    dashMock.dbStatus = 'ok';
    shellMock.sidebarCollapsed = false;
  });

  it('gives main an explicit desktop offset (expanded) — not an implicit flex reservation', () => {
    const html = render();
    expect(mainClass(html)).toContain('md:pl-[260px]');
  });

  it('tracks the collapsed rail width', () => {
    shellMock.sidebarCollapsed = true;
    expect(mainClass(render())).toContain('md:pl-[72px]');
  });

  it('renders the sidebar outside the main landmark (no nesting)', () => {
    const html = render();
    expect(html).toContain('data-testid="sidebar"');
    const main = html.slice(html.indexOf('<main'));
    expect(main).not.toContain('data-testid="sidebar"');
  });
});

describe('AppFrame — DB gate', () => {
  beforeEach(() => {
    navMock.pathname = '/portfolio';
    dashMock.dbStatus = 'ok';
    shellMock.sidebarCollapsed = false;
  });

  it('passes through when the backend is ok', () => {
    const html = render();
    expect(html).toContain('PAGE');
    expect(html).not.toContain('db-unavailable');
  });

  it('renders the honest panel, carrying the reason, on a gated route', () => {
    dashMock.dbStatus = 'unconfigured';
    const html = render();
    expect(html).toContain('data-testid="db-unavailable"');
    expect(html).toContain('data-status="unconfigured"');
    expect(html).not.toContain('PAGE');
  });

  it('distinguishes an unreachable backend from an unconfigured one', () => {
    dashMock.dbStatus = 'unreachable';
    expect(render()).toContain('data-status="unreachable"');
  });

  it('leaves the DB-exempt operator surface readable', () => {
    navMock.pathname = '/pipeline';
    dashMock.dbStatus = 'unreachable';
    const html = render();
    expect(html).toContain('PAGE');
    expect(html).not.toContain('db-unavailable');
  });

  it('leaves the static legacy redirect routes readable', () => {
    navMock.pathname = '/system';
    dashMock.dbStatus = 'unconfigured';
    expect(render()).toContain('PAGE');
  });
});
