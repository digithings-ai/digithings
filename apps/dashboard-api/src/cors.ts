/**
 * dashboard-api CORS (issue #4679).
 *
 * Mirrors `apps/digithings-stack-cloudflare/src/market-data.ts`: exact-match
 * origin allowlist, `Vary: Origin` on every response, `GET, OPTIONS` methods,
 * 86400s preflight cache, `OPTIONS` → 204 with an empty body.
 *
 * The reads served here are anon-readable house data (RLS `USING (true)`
 * pre-cutover posture), so CORS is a browser mechanism, not a secrecy
 * boundary — the allowlist names the dashboard origins, it does not guard
 * secrets (the service-role key never leaves the worker).
 */

/** Production dashboard + local dashboard dev servers. */
const DEFAULT_ORIGINS = [
  "https://digiquant.io",
  "https://digithings.ai",
  "http://localhost:3000",
  "http://127.0.0.1:3000",
  "http://localhost:3100",
  "http://127.0.0.1:3100",
  "http://localhost:3101",
  "http://127.0.0.1:3101",
].join(",");

export function resolveAllowlist(env: { DASHBOARD_API_ALLOWED_ORIGINS?: string }): string[] {
  return (env.DASHBOARD_API_ALLOWED_ORIGINS ?? DEFAULT_ORIGINS)
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function corsHeaders(origin: string | null, allowlist: string[]): Record<string, string> {
  const headers: Record<string, string> = { Vary: "Origin" };
  if (origin && allowlist.map((o) => o.trim()).includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS";
    headers["Access-Control-Max-Age"] = "86400";
  }
  return headers;
}

/** Attach CORS headers to any response (headers are immutable, so rebuild). */
export function withCors(res: Response, cors: Record<string, string>): Response {
  const headers = new Headers(res.headers);
  for (const [key, value] of Object.entries(cors)) headers.set(key, value);
  return new Response(res.body, { status: res.status, statusText: res.statusText, headers });
}
