/**
 * Billing CORS — a verbatim port of `digiquant/supabase/functions/_shared/cors.ts`.
 *
 * Deliberately DIFFERENT from the sibling `src/cors.ts`: that one is the
 * dashboard-api read allowlist (`Vary: Origin`, exact-match origins). Billing is
 * called by the authenticated dashboard origin with a bearer token and is
 * pre-cutover still served by the Supabase edge function, so these are the
 * exact permissive headers the edge function sends today. Contract parity with
 * the edge function outranks the house read policy for these three routes.
 */

export const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
};

export function corsPreflight(): Response {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}