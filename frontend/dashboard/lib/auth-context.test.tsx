/**
 * @vitest-environment happy-dom
 *
 * AuthProvider needs a real client effect cycle (getSession / onAuthStateChange /
 * setState). Other Olympus suites stay on node + renderToStaticMarkup; this file
 * opts into happy-dom only for the session lifecycle contract.
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';

type Listener = (event: string, session: unknown) => void;

const supabaseMock = vi.hoisted(() => {
  const listeners = new Set<Listener>();
  let session: { access_token: string; user: { id: string; email: string } } | null = null;

  const auth = {
    getSession: vi.fn(async () => ({ data: { session }, error: null })),
    onAuthStateChange: vi.fn((cb: Listener) => {
      listeners.add(cb);
      return {
        data: {
          subscription: {
            unsubscribe: () => {
              listeners.delete(cb);
            },
          },
        },
      };
    }),
    signInWithOAuth: vi.fn(async () => ({
      data: { url: 'https://accounts.example.test/oauth?state=1' },
      error: null,
    })),
    signInWithPassword: vi.fn(async () => ({ data: { session: null, user: null }, error: null })),
    signUp: vi.fn(async () => ({ data: { session: null, user: null }, error: null })),
    signOut: vi.fn(async () => {
      session = null;
      for (const cb of [...listeners]) cb('SIGNED_OUT', null);
      return { error: null };
    }),
  };

  return {
    listeners,
    auth,
    reset() {
      listeners.clear();
      session = null;
      auth.getSession.mockClear();
      auth.onAuthStateChange.mockClear();
      auth.signInWithOAuth.mockClear();
      auth.signInWithPassword.mockClear();
      auth.signUp.mockClear();
      auth.signOut.mockClear();
    },
    setSession(next: typeof session) {
      session = next;
    },
    client: { auth },
  };
});

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => supabaseMock.client,
}));

vi.mock('./supabase', async () => {
  const actual = await vi.importActual<typeof import('./supabase')>('./supabase');
  return {
    ...actual,
    isOlympusAuthEnabled: () => true,
    getSupabaseClient: () => supabaseMock.client,
    // Keep real oauthRedirectTo / olympusBasePath — do not stub the redirect URL.
  };
});

import { AuthProvider, useAuth } from './auth-context';

function Probe({
  onAuth,
}: {
  onAuth: (value: ReturnType<typeof useAuth>) => void;
}) {
  const auth = useAuth();
  onAuth(auth);
  return createElement(
    'div',
    {
      'data-email': auth.user?.email ?? '',
      'data-has-session': auth.session ? '1' : '0',
      'data-loading': auth.loading ? '1' : '0',
    },
    auth.user?.email ?? 'signed-out',
  );
}

describe('AuthProvider', () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: ReturnType<typeof useAuth> | null;

  beforeEach(() => {
    supabaseMock.reset();
    latest = null;
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  async function mountProbe() {
    await act(async () => {
      root.render(
        createElement(
          AuthProvider,
          null,
          createElement(Probe, {
            onAuth: (v) => {
              latest = v;
            },
          }),
        ),
      );
    });
    // Flush getSession promise
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it('hydrates session from supabase-js getSession (no network)', async () => {
    supabaseMock.setSession({
      access_token: 'tok',
      user: { id: 'u1', email: 'reader@example.com' },
    });
    await mountProbe();
    expect(container.textContent).toContain('reader@example.com');
    expect(latest?.user?.email).toBe('reader@example.com');
    expect(latest?.loading).toBe(false);
    expect(supabaseMock.auth.getSession).toHaveBeenCalled();
  });

  it('signOut clears session in context', async () => {
    supabaseMock.setSession({
      access_token: 'tok',
      user: { id: 'u1', email: 'reader@example.com' },
    });
    await mountProbe();
    expect(latest?.session).not.toBeNull();

    await act(async () => {
      await latest!.signOut();
    });

    expect(supabaseMock.auth.signOut).toHaveBeenCalled();
    expect(latest?.session).toBeNull();
    expect(latest?.user).toBeNull();
    expect(container.textContent).toContain('signed-out');
    expect(container.querySelector('[data-has-session="0"]')).not.toBeNull();
  });

  it('signInWithOAuth delegates to supabase-js with PKCE redirect including /dashboard', async () => {
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_BASE_PATH', '/dashboard');
    const assign = vi.fn();
    vi.stubGlobal('location', {
      origin: 'http://localhost:3000',
      assign,
    });
    await mountProbe();
    await act(async () => {
      await latest!.signInWithOAuth('github');
    });
    const call = supabaseMock.auth.signInWithOAuth.mock.calls[0]?.[0] as {
      provider: string;
      options: { redirectTo: string; skipBrowserRedirect?: boolean; queryParams?: unknown };
    };
    expect(call.provider).toBe('github');
    expect(call.options.skipBrowserRedirect).toBe(true);
    expect(call.options.queryParams).toBeUndefined();
    expect(call.options.redirectTo).toMatch(/\/dashboard\/auth\/callback\/$/);
    expect(call.options.redirectTo).toBe('http://localhost:3000/dashboard/auth/callback/');
    expect(assign).toHaveBeenCalledWith('https://accounts.example.test/oauth?state=1');
  });

  it('signInWithOAuth(google) sends offline + select_account query params', async () => {
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_BASE_PATH', '/dashboard');
    const assign = vi.fn();
    vi.stubGlobal('location', {
      origin: 'http://localhost:3000',
      assign,
    });
    await mountProbe();
    await act(async () => {
      await latest!.signInWithOAuth('google');
    });
    const call = supabaseMock.auth.signInWithOAuth.mock.calls[0]?.[0] as {
      provider: string;
      options: { queryParams?: Record<string, string>; skipBrowserRedirect?: boolean };
    };
    expect(call.provider).toBe('google');
    expect(call.options.skipBrowserRedirect).toBe(true);
    expect(call.options.queryParams).toEqual({
      access_type: 'offline',
      prompt: 'select_account',
    });
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it('signInWithOAuth throws when the provider returns no URL', async () => {
    supabaseMock.auth.signInWithOAuth.mockResolvedValueOnce({ data: {}, error: null });
    await mountProbe();
    await expect(latest!.signInWithOAuth('google')).rejects.toThrow(/Google did not return a redirect URL/);
  });

  it('signInWithPassword and signUpWithPassword delegate to supabase-js', async () => {
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_BASE_PATH', '/dashboard');
    vi.stubGlobal('location', { origin: 'http://localhost:3000', assign: vi.fn() });
    await mountProbe();
    await act(async () => {
      await latest!.signInWithPassword('a@b.c', 'secret12');
    });
    expect(supabaseMock.auth.signInWithPassword).toHaveBeenCalledWith({
      email: 'a@b.c',
      password: 'secret12',
    });
    let signupResult: { session: unknown } | undefined;
    await act(async () => {
      signupResult = await latest!.signUpWithPassword('a@b.c', 'secret12');
    });
    expect(supabaseMock.auth.signUp).toHaveBeenCalledWith({
      email: 'a@b.c',
      password: 'secret12',
      options: { emailRedirectTo: 'http://localhost:3000/dashboard/auth/callback/' },
    });
    expect(signupResult).toEqual({ session: null });
  });
});
