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
        detectSessionInUrl: true,
      },
    });
  }
  return createClient<Database>(url, key);
}

export const supabase: SupabaseClient<Database> | null =
  supabaseUrl && supabaseAnonKey
    ? buildSupabaseClient(supabaseUrl, supabaseAnonKey, isOlympusAuthEnabled())
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

/** OAuth redirect target for Google/GitHub PKCE (must match Supabase dashboard allow-list). */
export function oauthRedirectTo(): string {
  if (typeof window === 'undefined') return '';
  return `${window.location.origin}${olympusBasePath()}/auth/callback/`;
}
