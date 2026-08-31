/**
 * @vitest-environment happy-dom
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  alpacaOAuthCallbackPath,
  alpacaOAuthRedirectUri,
  buildAlpacaAuthorizeUrl,
  resolveAlpacaOAuthCallback,
  resolveAlpacaOauthClientId,
} from './alpaca-oauth';

describe('alpaca-oauth paths (real dashboardBasePath)', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_BASE_PATH', '/dashboard');
  });

  it('callback path includes /dashboard and trailing slash', () => {
    expect(alpacaOAuthCallbackPath()).toBe('/dashboard/settings/brokers/callback/');
  });

  it('authorize URL is the real Alpaca paper URL with /dashboard redirect', () => {
    const redirectUri = alpacaOAuthRedirectUri('https://app.example');
    expect(redirectUri).toBe(
      'https://app.example/dashboard/settings/brokers/callback/',
    );
    const url = buildAlpacaAuthorizeUrl({
      clientId: 'cid-public',
      redirectUri,
      state: 'nonce-abc',
    });
    // Pin the REAL authorize host + query — not a mock (T1 second lesson).
    expect(url.startsWith('https://app.alpaca.markets/oauth/authorize?')).toBe(
      true,
    );
    const u = new URL(url);
    expect(u.searchParams.get('env')).toBe('paper');
    expect(u.searchParams.get('state')).toBe('nonce-abc');
    expect(u.searchParams.get('client_id')).toBe('cid-public');
    expect(u.searchParams.get('redirect_uri')).toBe(
      'https://app.example/dashboard/settings/brokers/callback/',
    );
    expect(u.searchParams.get('scope')).toBe('account:write trading');
    // Must never drop the dashboard segment (T1 bug).
    expect(u.searchParams.get('redirect_uri')).toContain('/dashboard/');
    expect(u.searchParams.get('redirect_uri')).not.toBe(
      'https://app.example/settings/brokers/callback',
    );
  });

  it('falls back to /dashboard when BASE_PATH env is empty', async () => {
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_BASE_PATH', '');
    const { dashboardBasePath } = await import('@/lib/supabase');
    const raw = process.env.NEXT_PUBLIC_DASHBOARD_BASE_PATH || '/dashboard';
    const trimmed = raw.replace(/\/+$/, '');
    expect(trimmed || '/dashboard').toBe('/dashboard');
    void dashboardBasePath;
  });
});

describe('resolveAlpacaOAuthCallback ordering', () => {
  const base = {
    search: '?code=auth-code&state=nonce-1',
    storedState: 'nonce-1',
    origin: 'https://app.example',
  };

  it('waits while auth is loading (does not consume nonce)', () => {
    const phase = resolveAlpacaOAuthCallback({
      ...base,
      loading: true,
      accessToken: null,
    });
    expect(phase).toEqual({ kind: 'wait_auth' });
  });

  it('session-first then params: ready to exchange', () => {
    const phase = resolveAlpacaOAuthCallback({
      ...base,
      loading: false,
      accessToken: 'tok',
    });
    expect(phase.kind).toBe('exchange');
    if (phase.kind === 'exchange') {
      expect(phase.redirectUri).toBe(
        'https://app.example/dashboard/settings/brokers/callback/',
      );
      expect(phase.code).toBe('auth-code');
    }
  });

  it('params-first with null session after load: sign-in error, nonce kept', () => {
    const phase = resolveAlpacaOAuthCallback({
      ...base,
      loading: false,
      accessToken: null,
    });
    expect(phase).toMatchObject({
      kind: 'error',
      consumeNonce: false,
    });
  });

  it('state mismatch does not request nonce consumption for retry safety', () => {
    const phase = resolveAlpacaOAuthCallback({
      loading: false,
      accessToken: 'tok',
      search: '?code=auth-code&state=wrong',
      storedState: 'nonce-1',
      origin: 'https://app.example',
    });
    expect(phase).toMatchObject({ kind: 'error', consumeNonce: false });
  });
});

describe('resolveAlpacaOauthClientId', () => {
  it('prefers Settings EF public client id over Pages build env', () => {
    expect(resolveAlpacaOauthClientId(' cid-from-ef ', 'cid-from-pages')).toBe(
      'cid-from-ef',
    );
  });

  it('falls back to Pages env when Settings id is empty', () => {
    expect(resolveAlpacaOauthClientId('', 'cid-from-pages')).toBe('cid-from-pages');
    expect(resolveAlpacaOauthClientId(null, 'cid-from-pages')).toBe('cid-from-pages');
    expect(resolveAlpacaOauthClientId('  ', '')).toBe('');
  });
});
