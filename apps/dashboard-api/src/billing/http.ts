/**
 * Billing response primitives — a port of the `jsonError` / `jsonOk` pair from
 * `digiquant/supabase/functions/_shared/supabase-admin.ts`.
 *
 * NOT `src/responses.ts`: that module serves CONTRACT.md's `{ error: { code,
 * message, details, retrieval_pin } }` envelope. Billing has a different,
 * long-shipped wire contract — a flat `{ code, message }` body — and changing
 * it would break the dashboard's error handling at the moment of the cutover.
 * Wire parity is the whole point of this port.
 */

import { CORS_HEADERS } from "./cors";

export function jsonError(status: number, code: string, message: string): Response {
  return new Response(JSON.stringify({ code, message }), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}

export function jsonOk(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...CORS_HEADERS },
  });
}