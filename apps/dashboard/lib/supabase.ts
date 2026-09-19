import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Database } from './database.types';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? '';

/**
 * Feature flag for Supabase Auth login (T1). Default off → today's anon-only
 * behavior (Cloudflare Access remains the edge gate until cutover).
 * Inlined at build time — static export has no runtime env.
 */
export function isDashboardAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_DASHBOARD_AUTH === '1';
}

const FALLBACK_DASHBOARD_BASE_PATH = '/dashboard';

/**
 * App basePath for client URLs. Sourced from next.config.mjs `env` (same value
 * as `basePath: '/dashboard'`). Hard fallback keeps OAuth correct if env is missing.
 */
export function dashboardBasePath(): string {
  const raw = process.env.NEXT_PUBLIC_DASHBOARD_BASE_PATH || FALLBACK_DASHBOARD_BASE_PATH;
  const trimmed = raw.replace(/\/+$/, '');
  return trimmed || FALLBACK_DASHBOARD_BASE_PATH;
}

/**
 * Build the browser Supabase client.
 * - Flag off: plain anon client (no behavior change vs pre-T1; prerendered DOM
 *   verified identical under flag-off builds).
 * - Flag on: PKCE OAuth; session lives in supabase-js storage only (no custom cookies).
 */
export function buildSupabaseClient(
  url: string,
  key: string,
  authEnabled: boolean = isDashboardAuthEnabled(),
): SupabaseClient<Database> {
  if (authEnabled) {
    return createClient<Database>(url, key, {
      auth: {
        flowType: 'pkce',
        persistSession: true,
        autoRefreshToken: true,
        // Callback page owns `exchangeCodeForSession`. Auto-detect would
        // race the one-shot PKCE code (see PipelineClient).
        detectSessionInUrl: false,
      },
    });
  }
  return createClient<Database>(url, key);
}

export const supabase: SupabaseClient<Database> | null =
  supabaseUrl && supabaseAnonKey
    ? buildSupabaseClient(supabaseUrl, supabaseAnonKey, isDashboardAuthEnabled())
    : null;

/**
 * Session-aware accessor for the data layer. When auth is on, the same PKCE
 * client carries the user JWT (RLS scopes rows). When off, this is the anon
 * client — today's behavior.
 */
export function getSupabaseClient(): SupabaseClient<Database> | null {
  return supabase;
}

export const isSupabaseConfigured = (): boolean => Boolean(supabase);

/** Supabase OAuth 2.0 provider id. X is `x` (legacy Twitter OAuth 1.0a is off). UI copy is X. */
export type OAuthProvider = 'google' | 'github' | 'x';

/** OAuth redirect target for Google/GitHub PKCE (must match Supabase dashboard allow-list). */
export function oauthRedirectTo(): string {
  if (typeof window === 'undefined') return '';
  return `${window.location.origin}${dashboardBasePath()}/auth/callback/`;
}

/**
 * Options for supabase-js `signInWithOAuth`.
 *
 * `skipBrowserRedirect` is required: Google (unlike GitHub) often returns a URL
 * that the default supabase-js location swap drops on static `/dashboard/`
 * basePath. The caller assigns `data.url` itself after a missing-URL check.
 */
export function oauthSignInOptions(provider: OAuthProvider): {
  redirectTo: string;
  skipBrowserRedirect: true;
  queryParams?: Record<string, string>;
} {
  const options: {
    redirectTo: string;
    skipBrowserRedirect: true;
    queryParams?: Record<string, string>;
  } = {
    redirectTo: oauthRedirectTo(),
    skipBrowserRedirect: true,
  };
  if (provider === 'google') {
    options.queryParams = {
      access_type: 'offline',
      prompt: 'select_account',
    };
  }
  return options;
}

/** Parse `error` / `error_description` from the PKCE callback search or hash. */
export function oauthCallbackErrorFromLocation(search: string, hash: string): string | null {
  const query = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const hashParams = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash);
  const code = query.get('error') || hashParams.get('error');
  if (!code) return null;
  const desc = query.get('error_description') || hashParams.get('error_description');
  if (!desc) return code;
  try {
    return `${code}: ${decodeURIComponent(desc.replace(/\+/g, ' '))}`;
  } catch {
    return `${code}: ${desc}`;
  }
}

/** PKCE `code` query param on `/auth/callback/` (Google/GitHub both use this). */
export function oauthPkceCodeFromLocation(search: string): string | null {
  const query = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const code = query.get('code');
  return code && code.length > 0 ? code : null;
}
