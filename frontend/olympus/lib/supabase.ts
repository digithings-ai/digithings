import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Database } from './database.types';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? '';

/**
 * Feature flag for Supabase Auth login (T1). Default off → today's anon-only
 * behavior (Cloudflare Access remains the edge gate until cutover).
 * Inlined at build time — static export has no runtime env.
 */
export function isOlympusAuthEnabled(): boolean {
  return process.env.NEXT_PUBLIC_OLYMPUS_AUTH === '1';
}

/**
 * App basePath for client URLs. Sourced from next.config.mjs `env` (same value
 * as `basePath: '/olympus'`). Hard fallback keeps OAuth correct if env is missing.
 */
export function olympusBasePath(): string {
  const raw = process.env.NEXT_PUBLIC_OLYMPUS_BASE_PATH ?? '/olympus';
  const trimmed = raw.replace(/\/+$/, '');
  return trimmed || '/olympus';
}

/** GoTrue options that never restore a user JWT (role stays `anon`). */
const HOUSE_AUTH_OPTIONS = {
  persistSession: false,
  autoRefreshToken: false,
  detectSessionInUrl: false,
} as const;

/**
 * Session-less anon client for house Brief/Portfolio/Pipeline reads.
 * Must not share GoTrue storage with the PKCE singleton — a signed-in JWT
 * uses `role=authenticated`, and `anon_read` policies are `TO anon` only.
 * Until cutover 900, house rows stay on those anon policies.
 */
export function buildHouseSupabaseClient(
  url: string,
  key: string,
): SupabaseClient<Database> {
  return createClient<Database>(url, key, { auth: { ...HOUSE_AUTH_OPTIONS } });
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
  authEnabled: boolean = isOlympusAuthEnabled(),
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

const configured = Boolean(supabaseUrl && supabaseAnonKey);

/**
 * PKCE / session client. Login, Settings, and workspace-private RPCs only.
 * Do not use this for house dashboard reads while anon_read is still live.
 */
export const supabase: SupabaseClient<Database> | null = configured
  ? buildSupabaseClient(supabaseUrl, supabaseAnonKey, isOlympusAuthEnabled())
  : null;

/**
 * House corpus client (always session-less). Brief, Portfolio, Pipeline,
 * snapshot, and observability reads use this so a personal-workspace JWT
 * cannot hide house pipeline rows.
 */
export const supabaseHouse: SupabaseClient<Database> | null = configured
  ? buildHouseSupabaseClient(supabaseUrl, supabaseAnonKey)
  : null;

/**
 * Session-aware accessor for auth + Settings. House data layer uses
 * {@link getHouseSupabaseClient} instead.
 */
export function getSupabaseClient(): SupabaseClient<Database> | null {
  return supabase;
}

/** Session-less anon accessor for house dashboard queries. */
export function getHouseSupabaseClient(): SupabaseClient<Database> | null {
  return supabaseHouse;
}

export const isSupabaseConfigured = (): boolean => configured;

export type OAuthProvider = 'google' | 'github';

/** OAuth redirect target for Google/GitHub PKCE (must match Supabase dashboard allow-list). */
export function oauthRedirectTo(): string {
  if (typeof window === 'undefined') return '';
  return `${window.location.origin}${olympusBasePath()}/auth/callback/`;
}

/**
 * Options for supabase-js `signInWithOAuth`.
 *
 * `skipBrowserRedirect` is required: Google (unlike GitHub) often returns a URL
 * that the default supabase-js location swap drops on static `/olympus/`
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
