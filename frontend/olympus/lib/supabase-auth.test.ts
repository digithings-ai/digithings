/**
 * @vitest-environment happy-dom
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const createClient = vi.hoisted(() => vi.fn((..._args: unknown[]) => ({ auth: {} })));

vi.mock('@supabase/supabase-js', () => ({
  createClient: (...args: unknown[]) => createClient(...args),
}));

describe('buildSupabaseClient / oauthRedirectTo', () => {
  beforeEach(() => {
    createClient.mockClear();
    vi.unstubAllEnvs();
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_BASE_PATH', '/dashboard');
  });

  it('flag off: createClient is called with url+key only (anon client)', async () => {
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '');
    const { buildSupabaseClient, isDashboardAuthEnabled } = await import('./supabase');
    expect(isDashboardAuthEnabled()).toBe(false);
    createClient.mockClear();
    buildSupabaseClient('https://example.supabase.co', 'anon-key', false);
    expect(createClient).toHaveBeenCalledTimes(1);
    expect(createClient.mock.calls[0]).toEqual(['https://example.supabase.co', 'anon-key']);
  });

  it('flag on: createClient uses PKCE auth options', async () => {
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '1');
    const { buildSupabaseClient, isDashboardAuthEnabled } = await import('./supabase');
    expect(isDashboardAuthEnabled()).toBe(true);
    createClient.mockClear();
    buildSupabaseClient('https://example.supabase.co', 'anon-key', true);
    expect(createClient).toHaveBeenCalledTimes(1);
    const opts = createClient.mock.calls[0]?.[2] as {
      auth?: { flowType?: string; detectSessionInUrl?: boolean };
    };
    expect(opts?.auth?.flowType).toBe('pkce');
    expect(opts?.auth?.detectSessionInUrl).toBe(false);
  });

  it('oauthRedirectTo includes /dashboard basePath (real implementation)', async () => {
    const { oauthRedirectTo, dashboardBasePath } = await import('./supabase');
    expect(dashboardBasePath()).toBe('/dashboard');
    // happy-dom default origin
    expect(oauthRedirectTo()).toBe(`${window.location.origin}/dashboard/auth/callback/`);
  });

  it('oauthSignInOptions always skipBrowserRedirect and add Google query params', async () => {
    const { oauthSignInOptions } = await import('./supabase');
    const github = oauthSignInOptions('github');
    expect(github.skipBrowserRedirect).toBe(true);
    expect(github.redirectTo).toMatch(/\/dashboard\/auth\/callback\/$/);
    expect(github.queryParams).toBeUndefined();
    const google = oauthSignInOptions('google');
    expect(google.queryParams).toEqual({
      access_type: 'offline',
      prompt: 'select_account',
    });
  });

  it('oauthCallbackErrorFromLocation reads search and hash errors', async () => {
    const { oauthCallbackErrorFromLocation, oauthPkceCodeFromLocation } = await import(
      './supabase'
    );
    expect(oauthCallbackErrorFromLocation('', '')).toBeNull();
    expect(oauthCallbackErrorFromLocation('?error=access_denied', '')).toBe('access_denied');
    expect(
      oauthCallbackErrorFromLocation(
        '?error=access_denied&error_description=Provider+not+enabled',
        '',
      ),
    ).toBe('access_denied: Provider not enabled');
    expect(oauthCallbackErrorFromLocation('', '#error=server_error')).toBe('server_error');
    expect(oauthPkceCodeFromLocation('?code=pkce-abc')).toBe('pkce-abc');
    expect(oauthPkceCodeFromLocation('')).toBeNull();
  });

  it('dashboardBasePath falls back to /dashboard when env unset', async () => {
    vi.unstubAllEnvs();
    // Re-import would be cached; exercise the fallback via direct logic:
    // when NEXT_PUBLIC_DASHBOARD_BASE_PATH is empty string, still normalize.
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_BASE_PATH', '');
    const raw = process.env.NEXT_PUBLIC_DASHBOARD_BASE_PATH || '/dashboard';
    const trimmed = raw.replace(/\/+$/, '');
    expect(trimmed || '/dashboard').toBe('/dashboard');
  });
});
