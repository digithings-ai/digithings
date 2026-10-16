/**
 * Browser CORS for dashboard → core Edge Functions (Settings + billing).
 *
 * digiquant.io is a static Pages origin; Settings/Billing call
 * `*.supabase.co/functions/v1/*` with Authorization, which triggers an
 * OPTIONS preflight. Without Allow-* on the preflight (and on error
 * responses), Chromium fails with TypeError: Failed to fetch before the
 * JWT ever reaches the handler.
 */

export const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
};

/** 204 preflight — no body, no auth. */
export function corsPreflight(): Response {
  return new Response(null, { status: 204, headers: CORS_HEADERS });
}

/** Merge CORS onto an existing Response (preserves status/body). */
export function withCors(response: Response): Response {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(CORS_HEADERS)) {
    headers.set(key, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
