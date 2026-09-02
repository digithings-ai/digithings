/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const replace = vi.hoisted(() => vi.fn());
const supabaseMock = vi.hoisted(() => {
  const listeners = new Set<(event: string, session: unknown) => void>();
  const auth = {
    exchangeCodeForSession: vi.fn(async () => ({
      data: { session: { access_token: 't' } },
      error: null,
    })),
    getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    onAuthStateChange: vi.fn((cb: (event: string, session: unknown) => void) => {
      listeners.add(cb);
      return { data: { subscription: { unsubscribe: () => listeners.delete(cb) } } };
    }),
  };
  return {
    listeners,
    auth,
    client: { auth },
    reset() {
      listeners.clear();
      auth.exchangeCodeForSession.mockClear();
      auth.getSession.mockClear();
      auth.onAuthStateChange.mockClear();
      auth.getSession.mockResolvedValue({ data: { session: null }, error: null });
      auth.exchangeCodeForSession.mockResolvedValue({
        data: { session: { access_token: 't' } },
        error: null,
      });
    },
  };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
}));

vi.mock('next/link', () => ({
  default: (props: { children?: unknown; href?: string }) =>
    createElement('a', { href: props.href }, props.children as never),
}));

vi.mock('@/components/dashboard-mark', () => ({
  DashboardMark: () => createElement('span', null, 'mark'),
}));

vi.mock('@/lib/supabase', async () => {
  const actual = await vi.importActual<typeof import('@/lib/supabase')>('@/lib/supabase');
  return {
    ...actual,
    getSupabaseClient: () => supabaseMock.client,
  };
});

import AuthCallbackPage, { AUTH_CALLBACK_SETTLE_MS } from './page';

describe('AuthCallbackPage', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    supabaseMock.reset();
    replace.mockClear();
    window.history.replaceState({}, '', '/dashboard/auth/callback/');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    vi.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.useRealTimers();
  });

  async function mount() {
    await act(async () => {
      root.render(createElement(AuthCallbackPage));
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  }

  it('surfaces provider error_description and a return link', async () => {
    window.history.replaceState(
      {},
      '',
      '/dashboard/auth/callback/?error=access_denied&error_description=Provider+not+enabled',
    );
    await mount();
    expect(container.textContent).toContain('access_denied: Provider not enabled');
    expect(container.textContent).toContain('Return to sign in');
    expect(supabaseMock.auth.exchangeCodeForSession).not.toHaveBeenCalled();
  });

  it('exchanges ?code= and replaces home', async () => {
    window.history.replaceState({}, '', '/dashboard/auth/callback/?code=pkce-abc');
    await mount();
    expect(supabaseMock.auth.exchangeCodeForSession).toHaveBeenCalledWith('pkce-abc');
    expect(replace).toHaveBeenCalledWith('/');
  });

  it('does not navigate on INITIAL_SESSION while a PKCE code is still exchanging', async () => {
    let finishExchange: ((value: { data: { session: { access_token: string } }; error: null }) => void)
      | undefined;
    supabaseMock.auth.exchangeCodeForSession.mockImplementation(
      () =>
        new Promise((resolve) => {
          finishExchange = resolve;
        }),
    );
    window.history.replaceState({}, '', '/dashboard/auth/callback/?code=pkce-pending');
    await mount();
    expect(supabaseMock.auth.exchangeCodeForSession).toHaveBeenCalledWith('pkce-pending');
    await act(async () => {
      for (const cb of supabaseMock.listeners) {
        cb('INITIAL_SESSION', { access_token: 'stale' });
        cb('TOKEN_REFRESHED', { access_token: 'stale' });
      }
    });
    expect(replace).not.toHaveBeenCalled();
    await act(async () => {
      finishExchange?.({ data: { session: { access_token: 't' } }, error: null });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(replace).toHaveBeenCalledWith('/');
  });

  it('fails closed when the URL has neither code nor session', async () => {
    await mount();
    expect(container.textContent).toContain('Completing sign-in…');
    await act(async () => {
      vi.advanceTimersByTime(AUTH_CALLBACK_SETTLE_MS);
    });
    expect(container.textContent).toContain('Sign-in did not complete');
    expect(container.textContent).toContain('Return to sign in');
    expect(replace).not.toHaveBeenCalled();
  });
});
