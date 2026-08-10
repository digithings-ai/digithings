/**
 * Dedicated twelve-x (FX research) Supabase client.
 *
 * Reads the twelve-x-specific public env vars when present, falling back to the
 * main Olympus Supabase env vars when they are unset. This lets Olympus point
 * at a separate twelve-x project OR share the primary project transparently:
 *
 *   NEXT_PUBLIC_TWELVEX_SUPABASE_URL       (preferred)
 *   NEXT_PUBLIC_TWELVEX_SUPABASE_ANON_KEY  (preferred)
 *     ↓ fall back to
 *   NEXT_PUBLIC_SUPABASE_URL
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY
 *
 * Null-safe like {@link ../supabase}: the client is `null` when neither pair is
 * configured, and callers must guard with {@link isTwelveXConfigured}.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const twelveXUrl =
  process.env.NEXT_PUBLIC_TWELVEX_SUPABASE_URL ??
  process.env.NEXT_PUBLIC_SUPABASE_URL ??
  '';
const twelveXAnonKey =
  process.env.NEXT_PUBLIC_TWELVEX_SUPABASE_ANON_KEY ??
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??
  '';

/**
 * The twelve-x Supabase client, or `null` when no URL / anon key is configured.
 *
 * Untyped (`SupabaseClient` without a `Database` generic) on purpose: the
 * twelve-x FX tables live outside the main Olympus `database.types.ts`, and the
 * typed fetchers in `./fetch.ts` cast their selected rows to the contract types
 * in `./types.ts`.
 */
export const twelveXSupabase: SupabaseClient | null =
  twelveXUrl && twelveXAnonKey ? createClient(twelveXUrl, twelveXAnonKey) : null;

export const isTwelveXConfigured = (): boolean => Boolean(twelveXSupabase);
