/**
 * FX Hub response and caller-auth primitives.
 *
 * NOT `src/responses.ts`: that module serves the dashboard envelope. These
 * functions answer `{ ok, code, message? }`, which is the body the edge
 * functions already return. Wire parity is the point of the port.
 */

export function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Length check, then XOR accumulate. Mismatch on length returns immediately. */
export function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let acc = 0;
  for (let i = 0; i < a.length; i++) acc |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return acc === 0;
}

export function normalizeEmail(raw: unknown): string {
  return typeof raw === "string" ? raw.trim().toLowerCase() : "";
}

/**
 * Sends `input` after stripping an Authorization header that carries a
 * new-format API key.
 *
 * `sb_publishable_` / `sb_secret_` values are not JWTs. They belong on the
 * `apikey` header only; the platform answers `Invalid JWT` when one arrives
 * as `Bearer`. A header that does not match is left alone, so a genuine user
 * JWT (this module never has one) would still pass.
 */
export function apiKeyOnlyFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const headers = new Headers(
    init?.headers ?? (input instanceof Request ? input.headers : undefined),
  );
  const authorization = headers.get("Authorization") ?? "";
  if (/^Bearer (sb_publishable_|sb_secret_)/.test(authorization)) {
    headers.delete("Authorization");
  }
  if (input instanceof Request) {
    return fetch(new Request(input, { ...init, headers }));
  }
  return fetch(input, { ...init, headers });
}
