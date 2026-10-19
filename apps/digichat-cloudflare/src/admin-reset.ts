/**
 * Worker-owned recovery lever: destroy the shared digichat Container instance.
 *
 * With `max_instances = 1` (wrangler.toml), a Container instance that never
 * returns to `stopped` occupies the only slot and blocks every cold start — an
 * observed instance (the id pinned at the time) stayed `running` after minutes
 * of idleness despite `sleepAfter = "1m"`. `stop()` / `destroy()` exist only as
 * in-Durable Object methods, so the only recovery was deleting the whole
 * Cloudflare Container application. This is the Worker-side, secret-gated path
 * that calls `destroy()`, mirroring the pure-module shape of `occ-gate.ts` (it
 * has no Cloudflare-runtime imports, so it is unit-testable outside the Workers
 * runtime).
 *
 * Fail closed with **404**: an unset key, a missing header, or a mismatch all
 * return the identical not-found response, so a refusal never reveals whether a
 * key was valid. Non-POST methods answer `405` with `Allow: POST`, which
 * discloses only that the path is Worker-owned. The key is Worker-only and is
 * never forwarded to the Container.
 */
import { inviteTokenValid } from "./occ-gate";

/** The Worker holds the key; the Container never receives it (see index.ts `Env`). */
export const DIGICHAT_ADMIN_KEY_HEADER = "x-digi-admin-key";

/** One neutral body for every refusal — never echoes the key or the header. */
const NOT_FOUND_BODY = "digithings-digichat: not found";

/**
 * The reset route handler. The resolved Container id and `destroy` are injected
 * so the caller (index.ts) owns both the derivation from
 * `DIGICHAT_CONTAINER_REV` and `getContainer(...).destroy()`, and this module
 * stays dependency-free. The id is not a module constant: it follows the
 * deploying commit, and the proxy path addresses the same value.
 */
export async function digichatContainerReset(
  request: Request,
  expectedKey: string | undefined,
  instanceId: string,
  destroy: () => Promise<void>,
): Promise<Response> {
  if (request.method !== "POST") {
    return new Response("digithings-digichat: method not allowed", {
      status: 405,
      headers: { Allow: "POST" },
    });
  }
  // Constant-time compare with the same null-guard idiom as the OCC gate: an
  // unset expected key or a missing header is a refusal, not an error.
  const expected = expectedKey?.trim();
  const provided = request.headers.get(DIGICHAT_ADMIN_KEY_HEADER)?.trim() ?? null;
  if (!inviteTokenValid(provided, expected)) {
    return new Response(NOT_FOUND_BODY, { status: 404 });
  }
  await destroy();
  return Response.json({
    ok: true,
    action: "container_destroyed",
    instance: instanceId,
  });
}
