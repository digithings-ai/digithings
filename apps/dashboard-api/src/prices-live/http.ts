/**
 * Prices-live response primitive.
 *
 * NOT `src/responses.ts`: that module serves CONTRACT.md's
 * `{ error: { code, message, details, retrieval_pin } }` envelope.
 * The edge function answered with plain JSON bodies (`{ dormant }`,
 * `{ market }`, `{ skipped }`, the open-market report), and the dashboard
 * plus pg_cron log scraping parse those shapes today. Wire parity is the
 * whole point of this port, so the helper is the edge's `json()` verbatim.
 */

export function json(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
