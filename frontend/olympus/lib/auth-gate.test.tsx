import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Session, User } from '@supabase/supabase-js';

const authState = vi.hoisted(() => ({
  authEnabled: false,
  session: null as Session | null,
  user: null as User | null,
  loading: false,
  signInWithOAuth: vi.fn(async () => {}),
  signOut: vi.fn(async () => {}),
}));

const pathnameState = vi.hoisted(() => ({ value: '/' }));

/** When true, useSyncExternalStore client snapshot (post-mount). */
const mountedState = vi.hoisted(() => ({ client: true }));

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  return {
    ...actual,
    useSyncExternalStore: (
      _subscribe: () => () => void,
      getClient: () => boolean,
      getServer: () => boolean,
    ) => (mountedState.client ? getClient() : getServer()),
  };
});

vi.mock('next/navigation', () => ({
  usePathname: () => pathnameState.value,
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    authEnabled: authState.authEnabled,
    session: authState.session,
    user: authState.user,
    loading: authState.loading,
    signInWithOAuth: authState.signInWithOAuth,
    signOut: authState.signOut,
  }),
}));

vi.mock('@/lib/dashboard-context', () => ({
  DashboardProvider: ({ children }: { children: ReactNode }) =>
    createElement('div', { 'data-dashboard': '1' }, children),
}));

vi.mock('@/components/app-shell-context', () => ({
  AppShellProvider: ({ children }: { children: ReactNode }) =>
    createElement('div', { 'data-shell': '1' }, children),
}));

vi.mock('@/components/app-frame', () => ({
  default: ({ children }: { children: ReactNode }) =>
    createElement('div', { 'data-frame': '1' }, children),
}));

vi.mock('@/components/login-screen', () => ({
  LoginScreen: () => createElement('div', { 'data-login': '1' }, 'Sign in to digiquant'),
}));

vi.mock('@/components/atlas-mark', () => ({ DashboardMark: () => null, AtlasMark: () => null }));

import { AuthGate, isDashboardAuthCallbackPath, isDashboardAuthPath } from './auth-gate';

function renderGate(child = 'protected-child'): string {
  return renderToStaticMarkup(createElement(AuthGate, null, child));
}

describe('isDashboardAuthPath', () => {
  it('allows exact login, signup, and callback paths (with/without trailing slash)', () => {
    expect(isDashboardAuthPath('/login')).toBe(true);
    expect(isDashboardAuthPath('/login/')).toBe(true);
    expect(isDashboardAuthPath('/signup')).toBe(true);
    expect(isDashboardAuthPath('/signup/')).toBe(true);
    expect(isDashboardAuthPath('/auth/callback')).toBe(true);
    expect(isDashboardAuthPath('/auth/callback/')).toBe(true);
  });

  it('identifies only the PKCE callback as the exchange route', () => {
    expect(isDashboardAuthCallbackPath('/auth/callback')).toBe(true);
    expect(isDashboardAuthCallbackPath('/auth/callback/')).toBe(true);
    expect(isDashboardAuthCallbackPath('/dashboard/auth/callback')).toBe(true);
    expect(isDashboardAuthCallbackPath('/olympus/auth/callback')).toBe(false);
    expect(isDashboardAuthCallbackPath('/login')).toBe(false);
    expect(isDashboardAuthCallbackPath('/signup')).toBe(false);
  });

  it('allows basePath-prefixed exact forms and rejects the retired /olympus prefix', () => {
    expect(isDashboardAuthPath('/dashboard/login')).toBe(true);
    expect(isDashboardAuthPath('/dashboard/signup')).toBe(true);
    expect(isDashboardAuthPath('/dashboard/auth/callback/')).toBe(true);
    expect(isDashboardAuthPath('/olympus/login')).toBe(false);
    expect(isDashboardAuthPath('/olympus/signup')).toBe(false);
    expect(isDashboardAuthPath('/olympus/auth/callback/')).toBe(false);
  });

  it('rejects lookalike paths that previously bypassed via endsWith', () => {
    expect(isDashboardAuthPath('/settings/login')).toBe(false);
    expect(isDashboardAuthPath('/anything/login/')).toBe(false);
    expect(isDashboardAuthPath('/foo/auth/callback')).toBe(false);
    expect(isDashboardAuthPath('/')).toBe(false);
    expect(isDashboardAuthPath('/portfolio')).toBe(false);
    expect(isDashboardAuthPath(null)).toBe(false);
  });
});

describe('AuthGate', () => {
  beforeEach(() => {
    authState.authEnabled = false;
    authState.session = null;
    authState.user = null;
    authState.loading = false;
    pathnameState.value = '/';
    mountedState.client = true;
  });

  it('flag off: passes children through the app shell (today’s behavior)', () => {
    authState.authEnabled = false;
    const html = renderGate();
    expect(html).toContain('protected-child');
    expect(html).toContain('data-dashboard="1"');
    expect(html).toContain('data-frame="1"');
    expect(html).not.toContain('data-login');
  });

  it('flag on + prerender (!mounted): emits full shell, not loading or login', () => {
    authState.authEnabled = true;
    authState.session = null;
    authState.loading = true;
    mountedState.client = false;
    const html = renderGate();
    expect(html).toContain('protected-child');
    expect(html).toContain('data-frame="1"');
    expect(html).not.toContain('data-login');
    expect(html).not.toContain('Checking session');
  });

  it('flag on + mounted + no session: renders login UI, never empty chrome', () => {
    authState.authEnabled = true;
    authState.session = null;
    authState.loading = false;
    mountedState.client = true;
    const html = renderGate();
    expect(html).toContain('data-login="1"');
    expect(html).toContain('Sign in to digiquant');
    expect(html).not.toContain('protected-child');
    expect(html).not.toContain('data-frame');
  });

  it('flag on + mounted + session: renders children inside the app shell', () => {
    authState.authEnabled = true;
    authState.session = { access_token: 't' } as Session;
    authState.user = { id: 'u1', email: 'a@example.com' } as User;
    authState.loading = false;
    mountedState.client = true;
    const html = renderGate();
    expect(html).toContain('protected-child');
    expect(html).toContain('data-frame="1"');
    expect(html).not.toContain('data-login');
  });

  it('flag on + mounted + loading: shows session check, not empty chrome or children', () => {
    authState.authEnabled = true;
    authState.loading = true;
    authState.session = null;
    mountedState.client = true;
    const html = renderGate();
    expect(html).toContain('Checking session');
    expect(html).not.toContain('protected-child');
    expect(html).not.toContain('data-login');
  });

  it('flag on + auth route unsigned: renders children without shell', () => {
    authState.authEnabled = true;
    authState.session = null;
    pathnameState.value = '/login';
    mountedState.client = true;
    const html = renderGate();
    expect(html).toContain('protected-child');
    expect(html).not.toContain('data-frame');
    expect(html).not.toContain('data-login');
  });

  it('flag on + session on /login: leaves the auth card (email sign-in must not trap)', () => {
    authState.authEnabled = true;
    authState.session = { access_token: 't' } as Session;
    authState.user = { id: 'u1', email: 'a@example.com' } as User;
    authState.loading = false;
    pathnameState.value = '/login';
    mountedState.client = true;
    const html = renderGate();
    expect(html).toContain('Checking session');
    expect(html).not.toContain('protected-child');
    expect(html).not.toContain('data-frame');
  });

  it('flag on + session on /auth/callback: still renders the callback page', () => {
    authState.authEnabled = true;
    authState.session = { access_token: 't' } as Session;
    pathnameState.value = '/auth/callback';
    mountedState.client = true;
    const html = renderGate();
    expect(html).toContain('protected-child');
    expect(html).not.toContain('data-frame');
  });
});
