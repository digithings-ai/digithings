/**
 * @vitest-environment happy-dom
 *
 * AuthGate mounts this hook: unauthenticated visits stash `?invite=`,
 * then a later session auto-redeems. Login UI must not grow a code field.
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Session, User } from '@supabase/supabase-js';

const authState = vi.hoisted(() => ({
  authEnabled: true,
  session: null as Session | null,
  user: null as User | null,
  loading: false,
}));

const redeem = vi.hoisted(() => ({
  fn: vi.fn(async () => ({ ok: true, already_granted: false, product_key: 'fx_hub' })),
}));
const refresh = vi.hoisted(() => ({ fn: vi.fn() }));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    authEnabled: authState.authEnabled,
    session: authState.session,
    user: authState.user,
    loading: authState.loading,
  }),
}));

vi.mock('@/lib/settings-api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/settings-api')>('@/lib/settings-api');
  return {
    ...actual,
    redeemInvite: (...args: unknown[]) => redeem.fn(...args),
  };
});

vi.mock('@/lib/use-entitlement', () => ({
  requestAccessRefresh: () => refresh.fn(),
}));

import { useInviteLink } from './invite-link';
import { FX_HUB_INVITE_STORAGE_KEY } from './invite-stash';
import { SettingsHttpError } from './settings-api';

function Probe() {
  useInviteLink();
  return createElement('div', { 'data-testid': 'invite-probe' }, 'ok');
}

describe('useInviteLink', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    authState.authEnabled = true;
    authState.session = null;
    authState.user = null;
    authState.loading = false;
    redeem.fn.mockReset();
    redeem.fn.mockResolvedValue({ ok: true, already_granted: false, product_key: 'fx_hub' });
    refresh.fn.mockReset();
    sessionStorage.clear();
    window.history.replaceState(null, '', '/dashboard/');
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    sessionStorage.clear();
  });

  it('stashes invite while unsigned and auto-redeems after a session appears', async () => {
    window.history.replaceState(null, '', '/dashboard/?invite=fx-hub-desk-token');
    await act(async () => {
      root.render(createElement(Probe));
    });
    expect(sessionStorage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBe('fx-hub-desk-token');
    expect(window.location.search).not.toContain('invite=');
    expect(redeem.fn).not.toHaveBeenCalled();

    authState.session = {
      access_token: 'sess-tok',
      user: { id: 'u1', email: 'analyst@example.com' },
    } as Session;
    authState.user = { id: 'u1', email: 'analyst@example.com' } as User;
    await act(async () => {
      root.render(createElement(Probe));
    });

    expect(redeem.fn).toHaveBeenCalledWith(
      { accessToken: 'sess-tok' },
      { code: 'fx-hub-desk-token', product_key: 'fx_hub' },
    );
    expect(refresh.fn).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBeNull();
  });

  it('does not redeem a missing invite query', async () => {
    authState.session = {
      access_token: 'sess-tok',
      user: { id: 'u1', email: 'analyst@example.com' },
    } as Session;
    await act(async () => {
      root.render(createElement(Probe));
    });
    expect(redeem.fn).not.toHaveBeenCalled();
    expect(refresh.fn).not.toHaveBeenCalled();
  });

  it('does not grant when the stashed token is invalid', async () => {
    window.history.replaceState(null, '', '/dashboard/?invite=totally-wrong-invite');
    redeem.fn.mockRejectedValue(
      new SettingsHttpError({
        status: 403,
        code: 'INVITE_INVALID',
        message: 'Invite code is not valid.',
      }),
    );
    authState.session = {
      access_token: 'sess-tok',
      user: { id: 'u1', email: 'analyst@example.com' },
    } as Session;
    await act(async () => {
      root.render(createElement(Probe));
    });
    expect(redeem.fn).toHaveBeenCalledOnce();
    expect(refresh.fn).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(FX_HUB_INVITE_STORAGE_KEY)).toBeNull();
  });
});
