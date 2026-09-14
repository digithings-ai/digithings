/**
 * Bridges the dashboard's (core project) login into a real session on the
 * separate twelve-x Supabase project, via core's settings Edge Function
 * (`GET /access/twelvex-session`, gated on client_product_grants
 * product_key='fx_hub') and twelve-x's own `fx-hub-session` function.
 *
 * See lib/twelve-x/supabase.ts and AUTH.md's "twelve-x is a SEPARATE
 * Supabase project" section for why this exists instead of forwarding the
 * core JWT directly (Supabase's Third-Party Auth has no "trust another
 * Supabase project" option).
 */
import { getTwelveXSession as fetchTwelveXSession } from '../settings-api';
import { twelveXSupabase, isTwelveXConfigured } from './supabase';

export type TwelveXAuthClient = {
  getSession(): Promise<{ data: { session: unknown | null } }>;
  setSession(args: {
    access_token: string;
    refresh_token: string;
  }): Promise<{ error: unknown | null }>;
};

let inFlight: Promise<boolean> | null = null;

/**
 * Ensure the twelve-x client has a live session for `accessToken`'s owner.
 * No-op (and cheap) if a session is already set. Best-effort: on failure
 * (not yet granted, bridge unconfigured, network error) this resolves
 * `false` and callers proceed anyway — RLS then simply returns no rows
 * (this module's callers already render an empty state for that, matching
 * the existing "empty !== error" philosophy in lib/twelve-x/fetch.ts) rather
 * than the page hard-failing.
 *
 * `client` / `fetchSession` are injectable for tests; production callers
 * omit both and get the real twelve-x client + settings-api call.
 */
export async function ensureTwelveXSession(
  accessToken: string | undefined | null,
  deps: {
    client?: TwelveXAuthClient | null;
    fetchSession?: typeof fetchTwelveXSession;
  } = {},
): Promise<boolean> {
  const client = deps.client === undefined ? (twelveXSupabase?.auth ?? null) : deps.client;
  const fetchSession = deps.fetchSession ?? fetchTwelveXSession;

  if (!accessToken) return false;
  if (deps.client === undefined && !isTwelveXConfigured()) return false;
  if (!client) return false;

  const { data } = await client.getSession();
  if (data.session) return true;

  if (!inFlight) {
    inFlight = (async () => {
      try {
        const result = await fetchSession({ accessToken });
        const { error } = await client.setSession({
          access_token: result.access_token,
          refresh_token: result.refresh_token,
        });
        return !error;
      } catch {
        // Not yet granted, bridge unconfigured, or a network error — best-effort per the contract above.
        return false;
      } finally {
        inFlight = null;
      }
    })();
  }
  return inFlight;
}
