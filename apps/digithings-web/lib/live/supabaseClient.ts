/**
 * The digiquant band's read client, duplicated from
 * `apps/digiquant-web/lib/live/supabaseClient.ts` (#1461) at the owner's
 * instruction: "we need to do the same architecture as we have for the
 * DigiQuant website. We'll just duplicate it from there, so copy it over. We
 * will copy all the secrets and all the permissions. And they should share the
 * same canonical backend for getting all that data."
 *
 * digithings.ai is a static Cloudflare Pages export, so the anon key ships in
 * the bundle — the same posture digiquant.io already takes with the same key.
 * The client is exported as possibly-`null` so the static build succeeds WITHOUT
 * the public env vars set; the band falls back to its badged example series
 * until Cloudflare Pages has `NEXT_PUBLIC_SUPABASE_URL` and
 * `NEXT_PUBLIC_SUPABASE_ANON_KEY` (a human deploy step — copying "the secrets"
 * is setting those two vars on the Pages project, not putting them in the repo).
 *
 * SSR/static-export safe: `createClient` opens no socket at construction, and
 * the Realtime connection is lazy (first `.channel().subscribe()`), which only
 * ever runs inside client-side effects. Nothing here subscribes.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const supabase: SupabaseClient | null =
  supabaseUrl && supabaseAnonKey ? createClient(supabaseUrl, supabaseAnonKey) : null;

export const isSupabaseConfigured = (): boolean => Boolean(supabase);
