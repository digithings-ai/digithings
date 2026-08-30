/**
 * Typed fetchers for the Olympus settings Edge Function + T2 billing links (T3).
 * Session JWT goes in Authorization; only NEXT_PUBLIC_* in the static bundle.
 */

export type SettingsApiError = {
  code: string;
  message: string;
  status: number;
};

export class SettingsHttpError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(err: SettingsApiError) {
    super(err.message);
    this.name = 'SettingsHttpError';
    this.code = err.code;
    this.status = err.status;
  }
}

export type BrokerConnectionView = {
  id: string;
  broker: string;
  env: string;
  auth_kind?: string;
  fingerprint: string;
  status: string;
  last_used_at: string | null;
  created_at?: string;
};

export type ProfileSaveResult = {
  version_id: string;
  profile_key: string;
  schema_version: number;
  label: string;
  supersedes_id: string | null;
  recorded_at: string;
};

/** GET /profile tip (or empty contract when no tip yet). */
export type ProfileTip = {
  version_id: string | null;
  workspace_id: string;
  profile_key: string;
  schema_version: number;
  label: string;
  supersedes_id: string | null;
  recorded_at: string | null;
  investment: Record<string, unknown> | null;
  assets: Record<string, unknown> | null;
};

export type SettingsApiOptions = {
  /** Absolute or relative functions base, e.g. https://xxx.supabase.co/functions/v1 */
  functionsBaseUrl?: string;
  /** Access token from supabase.auth session. */
  accessToken: string;
  fetchImpl?: typeof fetch;
};

function functionsBase(): string {
  const explicit = process.env.NEXT_PUBLIC_SUPABASE_FUNCTIONS_URL?.replace(/\/$/, '');
  if (explicit) return explicit;
  const supabase = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, '');
  if (!supabase) return '';
  return `${supabase}/functions/v1`;
}

/** True when checkout/portal Edge Functions are addressable from the client. */
export function isBillingConfigured(): boolean {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL) return false;
  if (process.env.NEXT_PUBLIC_STRIPE_BILLING_ENABLED === '0') return false;
  return true;
}

async function request<T>(
  opts: SettingsApiOptions,
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const base = (opts.functionsBaseUrl ?? functionsBase()).replace(/\/$/, '');
  if (!base) {
    throw new SettingsHttpError({
      status: 500,
      code: 'NOT_CONFIGURED',
      message: 'Settings backend URL is not configured',
    });
  }
  const fetchImpl = opts.fetchImpl ?? fetch;
  const res = await fetchImpl(`${base}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${opts.accessToken}`,
      'Content-Type': 'application/json',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json: Record<string, unknown> = {};
  try {
    json = (await res.json()) as Record<string, unknown>;
  } catch {
    json = {};
  }
  if (!res.ok) {
    throw new SettingsHttpError({
      status: res.status,
      code: typeof json.code === 'string' ? json.code : 'HTTP_ERROR',
      message:
        typeof json.message === 'string' ? json.message : `HTTP ${res.status}`,
    });
  }
  return json as T;
}

export async function getProfile(
  opts: SettingsApiOptions,
  args?: { workspaceId?: string; profileKey?: string },
): Promise<ProfileTip> {
  const params = new URLSearchParams();
  if (args?.workspaceId) params.set('workspace_id', args.workspaceId);
  if (args?.profileKey) params.set('profile_key', args.profileKey);
  const q = params.toString() ? `?${params.toString()}` : '';
  return request<ProfileTip>(opts, 'GET', `/settings/profile${q}`);
}

export async function saveProfile(
  opts: SettingsApiOptions,
  payload: {
    profile_key: string;
    label: string;
    investment?: Record<string, unknown> | null;
    assets?: Record<string, unknown> | null;
    expected_version_id?: string | null;
    workspace_id?: string;
  },
): Promise<ProfileSaveResult> {
  return request<ProfileSaveResult>(opts, 'PATCH', '/settings/profile', payload);
}

export async function listBrokers(
  opts: SettingsApiOptions,
  workspaceId?: string,
): Promise<BrokerConnectionView[]> {
  const q = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
  const data = await request<{ connections: BrokerConnectionView[] }>(
    opts,
    'GET',
    `/settings/brokers${q}`,
  );
  return data.connections ?? [];
}

export async function connectBrokerApiKey(
  opts: SettingsApiOptions,
  payload: {
    broker: 'alpaca' | 'ibkr';
    env?: 'paper';
    key_id: string;
    secret: string;
    workspace_id?: string;
  },
): Promise<BrokerConnectionView> {
  return request<BrokerConnectionView>(opts, 'POST', '/settings/brokers/connect', {
    kind: 'api_key',
    env: 'paper',
    ...payload,
  });
}

export async function connectBrokerOAuth(
  opts: SettingsApiOptions,
  payload: {
    broker: 'alpaca';
    code: string;
    redirect_uri: string;
    workspace_id?: string;
  },
): Promise<BrokerConnectionView> {
  return request<BrokerConnectionView>(opts, 'POST', '/settings/brokers/connect', {
    kind: 'oauth',
    env: 'paper',
    ...payload,
  });
}

export async function revokeBroker(
  opts: SettingsApiOptions,
  payload: { connection_id: string; workspace_id?: string },
): Promise<BrokerConnectionView> {
  return request<BrokerConnectionView>(opts, 'POST', '/settings/brokers/revoke', payload);
}

export type NotificationPrefs = {
  workspace_id: string;
  email: string;
  daily_digest: boolean;
  holding_change_alerts: boolean;
  execution_alerts: boolean;
  digest_hour_utc: number;
  /** null when no persisted row yet (GET empty contract). */
  updated_at: string | null;
};

export async function getNotifications(
  opts: SettingsApiOptions,
  workspaceId?: string,
): Promise<NotificationPrefs> {
  const q = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : '';
  return request<NotificationPrefs>(opts, 'GET', `/settings/notifications${q}`);
}

export async function patchNotifications(
  opts: SettingsApiOptions,
  payload: {
    email?: string;
    daily_digest?: boolean;
    holding_change_alerts?: boolean;
    execution_alerts?: boolean;
    digest_hour_utc?: number;
    workspace_id?: string;
  },
): Promise<NotificationPrefs> {
  return request<NotificationPrefs>(opts, 'PATCH', '/settings/notifications', payload);
}

export async function createCheckoutSession(
  opts: SettingsApiOptions,
  payload: { tier: 'baseline' | 'custom'; interval?: 'monthly' | 'annual'; workspace_id?: string },
): Promise<{ id: string; url: string }> {
  return request(opts, 'POST', '/create-checkout-session', payload);
}

export async function createCustomerPortal(
  opts: SettingsApiOptions,
  payload: { workspace_id?: string } = {},
): Promise<{ url: string }> {
  return request(opts, 'POST', '/customer-portal', payload);
}
