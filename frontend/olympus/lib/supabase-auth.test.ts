import { beforeEach, describe, expect, it, vi } from 'vitest';

const createClient = vi.hoisted(() => vi.fn((..._args: unknown[]) => ({ auth: {} })));

vi.mock('@supabase/supabase-js', () => ({
  createClient: (...args: unknown[]) => createClient(...args),
}));

describe('buildSupabaseClient / flag-off anon path', () => {
  beforeEach(() => {
    createClient.mockClear();
    vi.unstubAllEnvs();
  });

  it('flag off: createClient is called with url+key only (anon client)', async () => {
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '');
    const { buildSupabaseClient, getSupabaseClientMode, isOlympusAuthEnabled } = await import(
      './supabase'
    );
    // Re-import after stub — module may already be cached; exercise builders directly.
    expect(isOlympusAuthEnabled()).toBe(false);
    expect(getSupabaseClientMode()).toBe('anon');
    createClient.mockClear();
    buildSupabaseClient('https://example.supabase.co', 'anon-key', false);
    expect(createClient).toHaveBeenCalledTimes(1);
    expect(createClient.mock.calls[0]).toEqual(['https://example.supabase.co', 'anon-key']);
  });

  it('flag on: createClient uses PKCE auth options', async () => {
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
    const { buildSupabaseClient, getSupabaseClientMode, isOlympusAuthEnabled } = await import(
      './supabase'
    );
    expect(isOlympusAuthEnabled()).toBe(true);
    expect(getSupabaseClientMode()).toBe('pkce');
    createClient.mockClear();
    buildSupabaseClient('https://example.supabase.co', 'anon-key', true);
    expect(createClient).toHaveBeenCalledTimes(1);
    const opts = createClient.mock.calls[0]?.[2] as { auth?: { flowType?: string } };
    expect(opts?.auth?.flowType).toBe('pkce');
  });
});
