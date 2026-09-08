import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, it, expect, vi } from 'vitest';

// Deterministic static render: stub the router, the app-shell context, and the
// leaf chrome so the test exercises only the nav composition.
vi.mock('next/navigation', () => ({ usePathname: () => '/' }));
vi.mock('@/components/app-shell-context', () => ({
  useAppShell: () => ({
    sidebarCollapsed: false,
    toggleSidebar: () => {},
    mobileNavOpen: false,
    setMobileNavOpen: () => {},
    toggleMobileNav: () => {},
    commandPaletteOpen: false,
    openCommandPalette: () => {},
    closeCommandPalette: () => {},
  }),
}));
vi.mock('@/components/sidebar-settings', () => ({ default: () => null }));
vi.mock('@/components/dashboard-mark', () => ({ DashboardMark: () => null }));

const authMock = vi.hoisted(() => ({
  authEnabled: false,
  session: null as { access_token: string } | null,
  user: null as { id: string; email: string } | null,
  loading: false,
  signInWithOAuth: vi.fn(async () => {}),
  signOut: vi.fn(async () => {}),
}));

vi.mock('@/lib/auth-context', async () => {
  const React = await vi.importActual<typeof import('react')>('react');
  return {
    AuthContext: React.createContext(null),
    useAuth: () => ({
      authEnabled: authMock.authEnabled,
      session: authMock.session,
      user: authMock.user,
      loading: authMock.loading,
      signInWithOAuth: authMock.signInWithOAuth,
      signOut: authMock.signOut,
    }),
  };
});
// next/link needs an app-router context at runtime; render its children inline.
vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import Sidebar from './sidebar';

describe('Sidebar', () => {
  beforeEach(() => {
    authMock.authEnabled = false;
    authMock.session = null;
    authMock.user = null;
    authMock.signOut.mockClear();
  });

  it('renders the owner destinations without System', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    for (const label of ['Brief', 'Portfolio', 'Pipeline', 'FX Hub']) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain('>System<');
    expect(html).not.toContain('System');
  });

  it('no longer shows the legacy labels', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html).not.toContain('Overview');
    expect(html).not.toContain('Observability');
    expect(html).not.toContain('Why');
  });

  it('flag off: does not render identity/sign-out chrome', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html).not.toContain('sidebar-auth-identity');
    expect(html).not.toContain('Sign out');
  });

  it('flag on + user: shows identity and sign-out control', () => {
    authMock.authEnabled = true;
    authMock.session = { access_token: 't' };
    authMock.user = { id: 'u1', email: 'owner@example.com' };
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html).toContain('data-testid="sidebar-auth-identity"');
    expect(html).toContain('owner@example.com');
    expect(html).toContain('Sign out');
    expect(html).toContain('aria-label="Sign out"');
  });
});
