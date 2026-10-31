import { embedHostOf, resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  toEmbedClientConfig,
} from "@/lib/embed-client-config";
import { inviteRequiredButMissing } from "@/lib/embed-invite-only";

/** Client-safe embed tenant config. Backend config (relay URLs) never leaves the server.
 *
 * The body is built from an allowlist of display fields (`toEmbedClientConfig`):
 * `access` (incl. `access.invite`), `token`, `tokenEnv` and other tenants'
 * documents never appear in it.
 *
 * Shares its projection with the `/embed` server render (embed-client-config.ts)
 * on purpose: the page paints from the server-resolved copy and this route then
 * re-asserts it, so the two must agree field-for-field or the re-assert would
 * repaint — the flash this indirection exists to remove.
 *
 * Fail closed: a host a gated tenant claims that did not resolve to that
 * tenant gets a plain 404 with no tenant detail, never the open default. */
export async function GET(req: Request): Promise<Response> {
  let cfg: ReturnType<typeof resolveVerifiedEmbedTenant>;
  try {
    cfg = resolveVerifiedEmbedTenant(req);
  } catch (error) {
    // Unreadable registry: deny, with the reason in the server log only.
    console.warn("[embed tenant-config] registry unreadable:", (error as Error).message);
    return notFound();
  }
  if (inviteRequiredButMissing(embedHostOf(req), cfg?.slug)) return notFound();
  const body = cfg ? toEmbedClientConfig(cfg) : DEFAULT_EMBED_TENANT_CONFIG;
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

function notFound(): Response {
  return new Response("Not found", {
    status: 404,
    headers: { "content-type": "text/plain", "cache-control": "no-store" },
  });
}
