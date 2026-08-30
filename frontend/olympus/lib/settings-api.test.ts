import { describe, expect, it, vi } from 'vitest';
import {
  connectBrokerApiKey,
  getNotifications,
  getProfile,
  isBillingConfigured,
  saveProfile,
  SettingsHttpError,
} from './settings-api';

describe('settings-api', () => {
  it('saveProfile sends Authorization and versioned payload', async () => {
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(init?.headers).toMatchObject({
        Authorization: 'Bearer tok',
      });
      const body = JSON.parse(String(init?.body));
      expect(body.profile_key).toBe('ws');
      expect(body.expected_version_id).toBe('v0');
      return new Response(
        JSON.stringify({
          version_id: 'v1',
          profile_key: 'ws',
          schema_version: 1,
          label: 'L',
          supersedes_id: 'v0',
          recorded_at: '2026-08-30T00:00:00Z',
        }),
        { status: 200 },
      );
    });
    const result = await saveProfile(
      {
        accessToken: 'tok',
        functionsBaseUrl: 'https://example.supabase.co/functions/v1',
        fetchImpl: fetchImpl as unknown as typeof fetch,
      },
      {
        profile_key: 'ws',
        label: 'L',
        expected_version_id: 'v0',
        investment: { risk_tolerance: 'moderate' },
      },
    );
    expect(result.version_id).toBe('v1');
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('connectBrokerApiKey posts api_key kind with env=paper', async () => {
    const secret = 'SUPER-SECRET-VALUE';
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({
          id: 'c1',
          broker: 'alpaca',
          env: 'paper',
          fingerprint: 'abcd1234',
          status: 'active',
          last_used_at: null,
        }),
        { status: 200 },
      ),
    );
    const row = await connectBrokerApiKey(
      {
        accessToken: 'tok',
        functionsBaseUrl: 'https://example.supabase.co/functions/v1',
        fetchImpl: fetchImpl as unknown as typeof fetch,
      },
      { broker: 'alpaca', key_id: 'PK', secret },
    );
    const sent = JSON.parse(String(fetchImpl.mock.calls[0]![1]?.body));
    expect(sent.kind).toBe('api_key');
    expect(sent.env).toBe('paper');
    expect(row.fingerprint).toBe('abcd1234');
    expect(JSON.stringify(row)).not.toContain(secret);
  });

  it('getNotifications GETs prefs and returns empty-contract shape', async () => {
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      expect(String(url)).toContain('/settings/notifications');
      expect(init?.method).toBe('GET');
      return new Response(
        JSON.stringify({
          workspace_id: 'ws-a',
          email: 'pm@example.com',
          daily_digest: false,
          holding_change_alerts: false,
          execution_alerts: false,
          digest_hour_utc: 12,
          updated_at: null,
        }),
        { status: 200 },
      );
    });
    const prefs = await getNotifications({
      accessToken: 'tok',
      functionsBaseUrl: 'https://example.supabase.co/functions/v1',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(prefs.updated_at).toBeNull();
    expect(prefs.digest_hour_utc).toBe(12);
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('getProfile GETs tip and returns empty-contract shape', async () => {
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      expect(String(url)).toContain('/settings/profile');
      expect(init?.method).toBe('GET');
      return new Response(
        JSON.stringify({
          version_id: null,
          workspace_id: 'ws-a',
          profile_key: 'workspace',
          schema_version: 1,
          label: '',
          supersedes_id: null,
          recorded_at: null,
          investment: null,
          assets: null,
        }),
        { status: 200 },
      );
    });
    const tip = await getProfile({
      accessToken: 'tok',
      functionsBaseUrl: 'https://example.supabase.co/functions/v1',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(tip.version_id).toBeNull();
    expect(tip.profile_key).toBe('workspace');
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it('maps 409 to SettingsHttpError', async () => {
    const fetchImpl = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ code: 'VERSION_CONFLICT', message: 'reload' }),
          { status: 409 },
        ),
    );
    await expect(
      saveProfile(
        {
          accessToken: 'tok',
          functionsBaseUrl: 'https://example.supabase.co/functions/v1',
          fetchImpl: fetchImpl as unknown as typeof fetch,
        },
        { profile_key: 'ws', label: 'L' },
      ),
    ).rejects.toMatchObject({ status: 409, code: 'VERSION_CONFLICT' } satisfies Partial<SettingsHttpError>);
  });

  it('isBillingConfigured is false without Supabase URL', () => {
    const prev = process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    expect(isBillingConfigured()).toBe(false);
    process.env.NEXT_PUBLIC_SUPABASE_URL = prev;
  });
});
