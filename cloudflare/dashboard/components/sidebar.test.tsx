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

const entitlementMock = vi.hoisted(() => ({
  canFxHub: true,
  effectivePlanTier: 'enterprise' as string,
}));

vi.mock('@/lib/use-entitlement', () => ({
  useCanAccessProduct: () => entitlementMock.canFxHub,
  useAccessSnapshot: () => ({ effectivePlanTier: entitlementMock.effectivePlanTier }),
}));

import Sidebar from './sidebar';

describe('Sidebar', () => {
  beforeEach(() => {
    authMock.authEnabled = false;
    authMock.session = null;
    authMock.user = null;
    authMock.signOut.mockClear();
    entitlementMock.canFxHub = true;
    entitlementMock.effectivePlanTier = 'enterprise';
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

  // The dedicated terminal entry (#4204): a flat external link in the nav's
  // bottom tools area — label, destination, and new-tab hardening.
  it('renders the dedicated Gloomberb Terminal entry', () => {
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html).toContain('Gloomberb Terminal');
    expect(html).toContain('data-testid="sidebar-gloomberb-link"');
    const anchor = html.match(/<a[^>]*data-testid="sidebar-gloomberb-link"[^>]*>/)?.[0] ?? '';
    expect(anchor).toContain('href="https://term.gloom.sh/"');
    expect(anchor).toContain('target="_blank"');
    expect(anchor).toContain('rel="noopener noreferrer"');
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

  it('an fx_hub-invited free-tier account sees ONLY FX Hub, no Brief/Portfolio/Pipeline', () => {
    entitlementMock.canFxHub = true;
    entitlementMock.effectivePlanTier = 'free';
    const html = renderToStaticMarkup(createElement(Sidebar));
    expect(html).toContain('FX Hub');
    for (const label of ['Brief', 'Portfolio', 'Pipeline']) {
      expect(html).not.toContain(label);
    }
    // Single-view contract: the terminal entry is a destination like any other.
    expect(html).not.toContain('Gloomberb Terminal');
    expect(html).not.toContain('sidebar-gloomberb-link');
  });

  it('a paying free-tier-on-paper but plan_floor-elevated account is unaffected', () => {
    // effectivePlanTier only reads 'free' for a genuinely unpaid account —
    // any real tier (brief/desk/studio/enterprise) sees the full spine
    // regardless of fx_hub, matching a normal paying customer or the
    // studio-floor creator/admin.
    entitlementMock.canFxHub = true;
    entitlementMock.effectivePlanTier = 'desk';
    const html = renderToStaticMarkup(createElement(Sidebar));
    for (const label of ['Brief', 'Portfolio', 'Pipeline', 'FX Hub']) {
      expect(html).toContain(label);
    }
  });

  it('a free-tier account without fx_hub sees neither FX Hub nor is nav-suppressed', () => {
    // No product grant at all (not an fx_hub invitee) — FX Hub hides as
    // before, but this is not the "invited, nothing else" case, so the
    // rest of the spine stays visible.
    entitlementMock.canFxHub = false;
    entitlementMock.effectivePlanTier = 'free';
    const html = renderToStaticMarkup(createElement(Sidebar));
    for (const label of ['Brief', 'Portfolio', 'Pipeline']) {
      expect(html).toContain(label);
    }
    expect(html).not.toContain('FX Hub');
  });
});
