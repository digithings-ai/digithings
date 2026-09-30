/**
 * @vitest-environment happy-dom
 */
import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  pathname: '/pipeline',
  dbStatus: 'ok' as 'ok' | 'down',
  fx: { canFxHub: true, fxHubOnlyInvitee: false },
}));

vi.mock('next/navigation', () => ({
  usePathname: () => state.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ dbStatus: state.dbStatus, data: null }),
}));
vi.mock('@/lib/fx-hub-only', () => ({
  useFxHubOnlyInvitee: () => state.fx,
  isFxHubOnlyAllowedPath: () => true,
}));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ authEnabled: false, user: null, signOut: vi.fn() }),
}));
vi.mock('@/components/theme-provider', () => ({
  useDashboardTheme: () => ({ theme: 'dark', effectiveTheme: 'dark', setTheme: vi.fn() }),
}));
vi.mock('@/components/app-shell-context', () => ({
  useAppShell: () => ({ openCommandPalette: vi.fn() }),
}));
vi.mock('@/components/command-palette', () => ({ default: () => null }));
vi.mock('@/components/digichat-popup', () => ({ default: () => null }));
vi.mock('@/components/settings-content', () => ({ SettingsContent: () => null }));
vi.mock('@/components/db-unavailable', () => ({
  default: () => createElement('div', { 'data-db-unavailable': '1' }),
}));

import DashboardShell from './dashboard-shell';

function render(children: ReactNode = createElement('p', null, 'page body')): string {
  return renderToStaticMarkup(createElement(DashboardShell, null, children));
}

describe('DashboardShell', () => {
  beforeEach(() => {
    state.pathname = '/pipeline';
    state.dbStatus = 'ok';
    state.fx = { canFxHub: true, fxHubOnlyInvitee: false };
  });

  it('renders exactly one main landmark that reserves the bar height', () => {
    const html = render();
    expect(html.match(/<main\b/g)).toHaveLength(1);
    expect(html).toContain('id="main"');
    expect(html).toContain('pt-(--nav-shell-h)');
    expect(html).toContain('page body');
  });

  it('is a top bar, not a sidebar: no aside, no app-sidebar-nav', () => {
    const html = render();
    expect(html).not.toContain('<aside');
    expect(html).not.toContain('app-sidebar-nav');
    expect(html).toContain('nav-shell');
  });

  it('lists the owner spine + Gloomberb, marks the pipeline current', () => {
    const html = render();
    for (const label of ['Brief', 'Portfolio', 'Pipeline', 'FX Hub', 'Gloomberb']) {
      expect(html).toContain(`>${label}`);
    }
    expect(html).toMatch(/href="\/dashboard\/pipeline\/"[^>]*aria-current="page"|aria-current="page"[^>]*href="\/dashboard\/pipeline\/"/);
  });

  it('DB down: gates a non-exempt route but keeps the bar mounted', () => {
    state.dbStatus = 'down';
    state.pathname = '/portfolio';
    const html = render();
    expect(html).toContain('data-db-unavailable');
    expect(html).not.toContain('page body');
    expect(html).toContain('nav-shell');
  });

  it('DB down: /pipeline is gated (nav.test pins it non-exempt), /settings stays live', () => {
    state.dbStatus = 'down';
    state.pathname = '/pipeline';
    expect(render()).toContain('data-db-unavailable');
    state.pathname = '/settings';
    const html = render();
    expect(html).not.toContain('data-db-unavailable');
    expect(html).toContain('page body');
  });

  it('fx_hub-only invitee sees FX Hub only — no spine, no Gloomberb', () => {
    state.fx = { canFxHub: true, fxHubOnlyInvitee: true };
    state.pathname = '/twelve-x';
    const html = render();
    expect(html).toContain('>FX Hub');
    for (const label of ['Brief', 'Portfolio', 'Pipeline', 'Gloomberb']) {
      expect(html).not.toContain(`>${label}`);
    }
  });
});
