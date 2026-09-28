import { describe, expect, it, vi } from 'vitest';
import { ensureTwelveXSession, type TwelveXAuthClient } from './session';

function fakeClient(initialSession: unknown | null = null): TwelveXAuthClient & {
  setSessionCalls: unknown[];
} {
  let session = initialSession;
  const setSessionCalls: unknown[] = [];
  return {
    setSessionCalls,
    getSession: async () => ({ data: { session } }),
    setSession: async (args) => {
      setSessionCalls.push(args);
      session = { access_token: args.access_token };
      return { error: null };
    },
  };
}

describe('ensureTwelveXSession', () => {
  it('returns false without an access token, never calling fetchSession', async () => {
    const client = fakeClient();
    const fetchSession = vi.fn();
    const ok = await ensureTwelveXSession(null, { client, fetchSession });
    expect(ok).toBe(false);
    expect(fetchSession).not.toHaveBeenCalled();
  });

  it('returns true immediately when a session already exists', async () => {
    const client = fakeClient({ access_token: 'existing' });
    const fetchSession = vi.fn();
    const ok = await ensureTwelveXSession('core-tok', { client, fetchSession });
    expect(ok).toBe(true);
    expect(fetchSession).not.toHaveBeenCalled();
  });

  it('mints and sets a session via the settings-api bridge when none exists', async () => {
    const client = fakeClient(null);
    const fetchSession = vi.fn(async () => ({
      ok: true as const,
      access_token: 'minted-access',
      refresh_token: 'minted-refresh',
      expires_in: 3600,
    }));
    const ok = await ensureTwelveXSession('core-tok', { client, fetchSession });
    expect(ok).toBe(true);
    expect(fetchSession).toHaveBeenCalledWith({ accessToken: 'core-tok' });
    expect(client.setSessionCalls).toEqual([
      { access_token: 'minted-access', refresh_token: 'minted-refresh' },
    ]);
  });

  it('resolves false (not throws) when the bridge is not granted / unconfigured', async () => {
    const client = fakeClient(null);
    const fetchSession = vi.fn(async () => {
      throw new Error('NOT_GRANTED');
    });
    const ok = await ensureTwelveXSession('core-tok', { client, fetchSession });
    expect(ok).toBe(false);
  });

  it('returns false when the client is explicitly null (twelve-x unconfigured)', async () => {
    const fetchSession = vi.fn();
    const ok = await ensureTwelveXSession('core-tok', { client: null, fetchSession });
    expect(ok).toBe(false);
    expect(fetchSession).not.toHaveBeenCalled();
  });
});
