/**
 * Alpaca OAuth path helpers (T3) — must use dashboardBasePath(), never an unset
 * NEXT_PUBLIC_BASE_PATH (that dropped the dashboard prefix — T1's exact bug).
 */

import { dashboardBasePath } from '@/lib/supabase';

export const ALPACA_OAUTH_STATE_KEY = 'dashboard_alpaca_oauth_state';

/** Fixed callback path under the dashboard basePath (trailing slash). */
export function alpacaOAuthCallbackPath(): string {
  return `${dashboardBasePath()}/settings/brokers/callback/`;
}

/** Absolute redirect_uri for authorize + token exchange. */
export function alpacaOAuthRedirectUri(origin: string = window.location.origin): string {
  return `${origin.replace(/\/$/, '')}${alpacaOAuthCallbackPath()}`;
}

/** Settings home after a successful connect. */
export function settingsHomeHref(): string {
  return `${dashboardBasePath()}/settings/`;
}

/** Alpaca OAuth authorize URL (paper). Client id is public; secret stays server-side. */
export function buildAlpacaAuthorizeUrl(args: {
  clientId: string;
  redirectUri: string;
  state: string;
}): string {
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: args.clientId,
    redirect_uri: args.redirectUri,
    scope: 'account:write trading',
    state: args.state,
    env: 'paper',
  });
  return `https://app.alpaca.markets/oauth/authorize?${params.toString()}`;
}

export function publicAlpacaClientId(): string {
  return process.env.NEXT_PUBLIC_ALPACA_OAUTH_CLIENT_ID ?? '';
}

/** Prefer the Settings EF public client id (runtime secret) over the Pages build env. */
export function resolveAlpacaOauthClientId(
  fromSettings: string | null | undefined,
  fromBuildEnv: string = publicAlpacaClientId(),
): string {
  const api = (fromSettings ?? '').trim();
  if (api.length > 0) return api;
  return fromBuildEnv.trim();
}

export type OAuthCallbackPhase =
  | { kind: 'wait_auth' }
  | { kind: 'error'; message: string; consumeNonce: false }
  | {
      kind: 'exchange';
      code: string;
      state: string;
      stored: string;
      redirectUri: string;
    };

/**
 * Decide what the callback page should do given auth hydration + URL params.
 *
 * - While `loading`, wait (do NOT touch sessionStorage).
 * - On mismatch / missing params: error without consuming the nonce when we
 *   never had a chance to exchange (so a later hydrated run can still succeed
 *   only if we hadn't consumed — callers must not remove until exchange ok).
 * - On ready + matching state: return exchange intent; caller removes nonce
 *   ONLY after a successful connectBrokerOAuth.
 */
export function resolveAlpacaOAuthCallback(args: {
  loading: boolean;
  accessToken: string | null | undefined;
  search: string;
  storedState: string | null;
  origin: string;
}): OAuthCallbackPhase {
  if (args.loading) return { kind: 'wait_auth' };

  const params = new URLSearchParams(
    args.search.startsWith('?') ? args.search.slice(1) : args.search,
  );
  const code = params.get('code');
  const state = params.get('state');
  const stored = args.storedState;

  if (!code || !state || !stored || state !== stored) {
    return {
      kind: 'error',
      message: 'OAuth state mismatch — return to Brokers and try again.',
      consumeNonce: false,
    };
  }
  if (!args.accessToken) {
    return {
      kind: 'error',
      message: 'Sign in required to finish broker connect.',
      consumeNonce: false,
    };
  }
  return {
    kind: 'exchange',
    code,
    state,
    stored,
    redirectUri: alpacaOAuthRedirectUri(args.origin),
  };
}
