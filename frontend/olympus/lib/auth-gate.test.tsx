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

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
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
  LoginScreen: () => createElement('div', { 'data-login': '1' }, 'Sign in to Olympus'),
}));

vi.mock('@/components/atlas-mark', () => ({ AtlasMark: () => null }));

import { AuthGate } from './auth-gate';

function renderGate(child = 'protected-child'): string {
  return renderToStaticMarkup(createElement(AuthGate, null, child));
}

describe('AuthGate', () => {
  beforeEach(() => {
    authState.authEnabled = false;
    authState.session = null;
    authState.user = null;
    authState.loading = false;
  });

  it('flag off: passes children through the app shell (today’s behavior)', () => {
    authState.authEnabled = false;
    const html = renderGate();
    expect(html).toContain('protected-child');
    expect(html).toContain('data-dashboard="1"');
    expect(html).toContain('data-frame="1"');
    expect(html).not.toContain('data-login');
  });

  it('flag on + no session: renders login UI, never empty chrome', () => {
    authState.authEnabled = true;
    authState.session = null;
    authState.loading = false;
    const html = renderGate();
    expect(html).toContain('data-login="1"');
    expect(html).toContain('Sign in to Olympus');
    expect(html).not.toContain('protected-child');
    expect(html).not.toContain('data-frame');
  });

  it('flag on + session: renders children inside the app shell', () => {
    authState.authEnabled = true;
    authState.session = { access_token: 't' } as Session;
    authState.user = { id: 'u1', email: 'a@example.com' } as User;
    authState.loading = false;
    const html = renderGate();
    expect(html).toContain('protected-child');
    expect(html).toContain('data-frame="1"');
    expect(html).not.toContain('data-login');
  });

  it('flag on + loading: shows session check, not empty chrome or children', () => {
    authState.authEnabled = true;
    authState.loading = true;
    authState.session = null;
    const html = renderGate();
    expect(html).toContain('Checking session');
    expect(html).not.toContain('protected-child');
    expect(html).not.toContain('data-login');
  });
});
