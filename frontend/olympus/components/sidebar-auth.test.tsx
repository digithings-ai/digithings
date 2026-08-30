/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest';

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
vi.mock('next/link', () => ({
  default: (props: { children?: unknown; href?: string }) =>
    createElement('a', { href: props.href }, props.children as never),
}));

const authMock = vi.hoisted(() => ({
  authEnabled: true,
  session: { access_token: 't' } as { access_token: string } | null,
  user: { id: 'u1', email: 'owner@example.com' } as { id: string; email: string } | null,
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

import Sidebar from './sidebar';

describe('Sidebar auth identity (happy-dom)', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    authMock.authEnabled = true;
    authMock.session = { access_token: 't' };
    authMock.user = { id: 'u1', email: 'owner@example.com' };
    authMock.signOut.mockClear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('renders identity and invokes signOut on click', async () => {
    await act(async () => {
      root.render(createElement(Sidebar));
    });

    expect(container.textContent).toContain('owner@example.com');
    const btn = container.querySelector('button[aria-label="Sign out"]');
    expect(btn).not.toBeNull();

    await act(async () => {
      btn!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    expect(authMock.signOut).toHaveBeenCalledTimes(1);
  });
});
