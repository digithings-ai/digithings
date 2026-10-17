/**
 * Dedicated twelve-x (FX research) Supabase client.
 *
 * Reads the twelve-x-specific public env vars when present, falling back to the
 * main dashboard Supabase env vars when they are unset. This lets dashboard point
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
 * twelve-x FX tables live outside the main dashboard `database.types.ts`, and the
 * typed fetchers in `./fetch.ts` cast their selected rows to the contract types
 * in `./types.ts`.
 *
 * Starts on the anon key alone, and since the cutover that key alone reads
 * nothing: the RLS cutover was promoted on 2026-09-14 in the twelve-x repo
 * (`supabase/migrations/028_fx_hub_rls_cutover.sql`, with
 * `029_fx_hub_rls_access_fix.sql` swapping its inline `fx_hub_grants`
 * subquery for a SECURITY DEFINER `fx_hub_has_access()` helper), so the
 * `anon` role holds no read grant on the `fx_*` tables. Reads therefore
 * depend on `./session.ts`: `ensureTwelveXSession()` calls `auth.setSession()`
 * with a session minted server-side by twelve-x's own `fx-hub-session` Edge
 * Function — see that file for why (Supabase's Third-Party Auth only
 * supports named identity providers, not "trust another Supabase project",
 * so this project needs its own real session rather than a forwarded JWT).
 * `persistSession: true` (own storage key, distinct from the dashboard auth
 * singleton) so the minted session survives reloads within its ~1hr expiry.
 */
/** Secondary client: never share GoTrue storage with the dashboard auth singleton. */
export const twelveXSupabase: SupabaseClient | null =
  twelveXUrl && twelveXAnonKey
    ? createClient(twelveXUrl, twelveXAnonKey, {
        auth: {
          storageKey: 'twelvex-auth',
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: false,
        },
      })
    : null;

export const isTwelveXConfigured = (): boolean => Boolean(twelveXSupabase);
