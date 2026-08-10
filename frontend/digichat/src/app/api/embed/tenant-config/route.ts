import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  toEmbedClientConfig,
} from "@/lib/embed-client-config";

/** Client-safe embed tenant config. Backend config (relay URLs) never leaves the server.
 *
 * Shares its projection with the `/embed` server render (embed-client-config.ts)
 * on purpose: the page paints from the server-resolved copy and this route then
 * re-asserts it, so the two must agree field-for-field or the re-assert would
 * repaint — the flash this indirection exists to remove. */
export async function GET(req: Request): Promise<Response> {
  const cfg = resolveVerifiedEmbedTenant(req);
  const body = cfg ? toEmbedClientConfig(cfg) : DEFAULT_EMBED_TENANT_CONFIG;
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
