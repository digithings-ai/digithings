import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

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
vi.mock('@/components/atlas-mark', () => ({ AtlasMark: () => null }));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    authEnabled: false,
    session: null,
    user: null,
    loading: false,
    signInWithOAuth: async () => {},
    signOut: async () => {},
  }),
}));
// next/link needs an app-router context at runtime; render its children inline.
vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import Sidebar from './sidebar';

describe('Sidebar', () => {
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
});
