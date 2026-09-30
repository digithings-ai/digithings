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
  tier: 'enterprise',
  collapsed: false,
}));

vi.mock('next/navigation', () => ({
  usePathname: () => state.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) =>
    createElement('a', { href, ...rest }, children),
}));
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ dbStatus: state.dbStatus, data: null }),
}));
vi.mock('@/lib/fx-hub-only', () => ({
  useFxHubOnlyInvitee: () => state.fx,
  isFxHubOnlyAllowedPath: () => true,
}));
vi.mock('@/lib/use-entitlement', () => ({ usePlanTier: () => state.tier }));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ authEnabled: false, user: null, signOut: vi.fn() }),
}));
vi.mock('@/components/theme-provider', () => ({
  useDashboardTheme: () => ({ theme: 'dark', effectiveTheme: 'dark', setTheme: vi.fn() }),
}));
vi.mock('@/components/app-shell-context', () => ({
  useAppShell: () => ({
    sidebarCollapsed: state.collapsed,
    toggleSidebar: vi.fn(),
    setSidebarCollapsed: vi.fn(),
    sidebarWidth: 240,
    setSidebarWidth: vi.fn(),
    sidebarDefault: 'expanded',
    setSidebarDefault: vi.fn(),
    openGroups: [],
    toggleGroup: vi.fn(),
    statusOpen: true,
    toggleStatus: vi.fn(),
    density: 'compact',
    setDensity: vi.fn(),
    openCommandPalette: vi.fn(),
  }),
}));
vi.mock('@/components/command-palette', () => ({ default: () => null }));
vi.mock('@/components/digichat-popup', () => ({ default: () => null }));
vi.mock('@/components/db-unavailable', () => ({
  default: () => createElement('div', { 'data-db-unavailable': '1' }),
}));

import AppShell from './app-shell';

function render(children: ReactNode = createElement('p', null, 'page body')): string {
  return renderToStaticMarkup(createElement(AppShell, null, children));
}

describe('AppShell', () => {
  beforeEach(() => {
    state.pathname = '/pipeline';
    state.dbStatus = 'ok';
    state.fx = { canFxHub: true, fxHubOnlyInvitee: false };
    state.tier = 'enterprise';
    state.collapsed = false;
  });

  it('renders exactly one main landmark, a sidebar sibling and one h1', () => {
    const html = render();
    expect(html.match(/<main\b/g)).toHaveLength(1);
    expect(html).toContain('id="main"');
    expect(html).toContain('id="app-sidebar-nav"');
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toContain('>Pipeline</h1>');
    expect(html).toContain('page body');
  });

  it('lists the spine, Gloomberb, and marks the current destination', () => {
    const html = render();
    for (const label of ['Brief', 'Portfolio', 'Pipeline', 'FX Hub', 'House', 'Gloomberb Terminal', 'Settings']) {
      expect(html).toContain(label);
    }
    expect(html).toMatch(/href="\/pipeline"[^>]*aria-current="page"|aria-current="page"[^>]*href="\/pipeline"/);
    expect(html).toContain('data-testid="sidebar-gloomberb-link"');
  });

  it('renders the adjustable width and a resize handle when expanded', () => {
    const html = render();
    expect(html).toContain('--sidebar-width:240px');
    expect(html).toContain('role="separator"');
  });

  it('collapses to the icon rail', () => {
    state.collapsed = true;
    const html = render();
    expect(html).toContain('data-collapsible="icon"');
    expect(html).not.toContain('role="separator"');
  });

  it('DB down: gates a non-exempt route but keeps the shell; /settings stays live', () => {
    state.dbStatus = 'down';
    state.pathname = '/portfolio';
    let html = render();
    expect(html).toContain('data-db-unavailable');
    expect(html).not.toContain('page body');
    expect(html).toContain('id="app-sidebar-nav"');
    state.pathname = '/settings';
    html = render();
    expect(html).not.toContain('data-db-unavailable');
    expect(html).toContain('page body');
  });

  it('settings children omit tabs the tier cannot use', () => {
    state.tier = 'free';
    state.pathname = '/settings';
    const html = render();
    expect(html).toContain('settings-tab-billing');
    expect(html).not.toContain('settings-tab-brokers');
  });

  it('fx_hub-only invitee sees FX Hub and Account only — no spine, no Gloomberb', () => {
    state.fx = { canFxHub: true, fxHubOnlyInvitee: true };
    state.pathname = '/twelve-x';
    const html = render();
    expect(html).toContain('FX Hub');
    for (const label of ['>Brief<', '>Portfolio<', '>Pipeline<', 'Gloomberb', '>House<']) {
      expect(html).not.toContain(label);
    }
    expect(html).toContain('Account');
  });
});
