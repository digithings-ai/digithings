import { describe, expect, it, vi } from 'vitest';
import {
  connectBrokerApiKey,
  connectProviderKey,
  getAppUrls,
  getFills,
  getJobs,
  getNotificationLog,
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

  it('connectProviderKey posts api_key kind without echoing secret in response path', async () => {
    const secret = 'sk-never-in-row';
    const fetchImpl = vi.fn(async () =>
      new Response(
        JSON.stringify({
          id: 'k1',
          provider: 'openai',
          fingerprint: 'abcd1234',
          status: 'active',
          last_used_at: null,
        }),
        { status: 200 },
      ),
    );
    const row = await connectProviderKey(
      {
        accessToken: 'tok',
        functionsBaseUrl: 'https://example.supabase.co/functions/v1',
        fetchImpl: fetchImpl as unknown as typeof fetch,
      },
      { provider: 'openai', secret },
    );
    const sent = JSON.parse(String(fetchImpl.mock.calls[0]![1]?.body));
    expect(sent.kind).toBe('api_key');
    expect(sent.provider).toBe('openai');
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

  it('getJobs GETs member-scoped job_runs', async () => {
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      expect(String(url)).toContain('/settings/jobs');
      expect(init?.method).toBe('GET');
      return new Response(
        JSON.stringify({
          jobs: [
            {
              id: 'job-a',
              job_type: 'overlay_daily',
              status: 'succeeded',
              error: null,
              idempotency_key: 'k',
              started_at: '2026-08-31T00:00:00Z',
              finished_at: '2026-08-31T00:01:00Z',
            },
          ],
        }),
        { status: 200 },
      );
    });
    const jobs = await getJobs({
      accessToken: 'tok',
      functionsBaseUrl: 'https://example.supabase.co/functions/v1',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(jobs).toHaveLength(1);
    expect(jobs[0]?.job_type).toBe('overlay_daily');
  });

  it('getFills omits broker external ids from the typed view', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      expect(String(url)).toContain('/settings/fills');
      return new Response(
        JSON.stringify({
          fills: [
            {
              id: 'f1',
              symbol: 'AAPL',
              quantity: 1,
              executed_at: '2026-08-31T14:00:00Z',
              recorded_at: '2026-08-31T14:00:01Z',
            },
          ],
        }),
        { status: 200 },
      );
    });
    const fills = await getFills({
      accessToken: 'tok',
      functionsBaseUrl: 'https://example.supabase.co/functions/v1',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(fills[0]?.symbol).toBe('AAPL');
    expect(JSON.stringify(fills)).not.toContain('external_fill_id');
  });

  it('getNotificationLog GETs digest event keys', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      expect(String(url)).toContain('/settings/notifications/log');
      return new Response(
        JSON.stringify({
          events: [{ event_key: 'digest:2026-08-31', sent_date: '2026-08-31', sent_at: 't' }],
        }),
        { status: 200 },
      );
    });
    const events = await getNotificationLog({
      accessToken: 'tok',
      functionsBaseUrl: 'https://example.supabase.co/functions/v1',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(events[0]?.event_key).toBe('digest:2026-08-31');
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

  it('getAppUrls returns public client id and never a secret field', async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      expect(String(url)).toContain('/settings/app-urls');
      return new Response(
        JSON.stringify({
          alpaca_redirect_uri: 'https://digiquant.io/olympus/settings/brokers/callback/',
          billing_return_url: 'https://digiquant.io/olympus/settings/?tab=billing',
          alpaca_oauth_client_id: 'cid-public',
        }),
        { status: 200 },
      );
    });
    const urls = await getAppUrls({
      accessToken: 'tok',
      functionsBaseUrl: 'https://example.supabase.co/functions/v1',
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    expect(urls.alpaca_oauth_client_id).toBe('cid-public');
    expect(JSON.stringify(urls)).not.toMatch(/secret/i);
  });
});
