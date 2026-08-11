/**
 * Browser Supabase client singleton for digiquant.io (#1461).
 *
 * digiquant.io is a static Cloudflare Pages export — the anon key ships in the
 * bundle. Mirrors olympus/lib/supabase.ts in spirit: the client is exported as
 * possibly-`null` so the static build succeeds WITHOUT the public env vars set.
 * It lights up once Cloudflare Pages has `NEXT_PUBLIC_SUPABASE_URL` +
 * `NEXT_PUBLIC_SUPABASE_ANON_KEY` (a human deploy step). Until then the live
 * layer degrades to the daily-close fallback.
 *
 * SSR/static-export safe: `createClient` opens no socket at construction — the
 * Realtime connection is lazy (first `.channel().subscribe()`), which only runs
 * inside client-side effects.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const supabase: SupabaseClient | null =
  supabaseUrl && supabaseAnonKey ? createClient(supabaseUrl, supabaseAnonKey) : null;

export const isSupabaseConfigured = (): boolean => Boolean(supabase);
