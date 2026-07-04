import type { ChatTenantContext } from "@/lib/chat-route-context";
import { resolveEmbedTenantByHost, type EmbedTenantConfig } from "@/lib/embed-tenants";

export type EmbedChatTenantContext = ChatTenantContext & {
  embedConfig: EmbedTenantConfig | null;
};

/** Extracts the embed config from either tenant context variant, or null when absent. */
export function embedConfigOf(
  ctx: ChatTenantContext | EmbedChatTenantContext
): EmbedTenantConfig | null {
  return "embedConfig" in ctx ? ctx.embedConfig : null;
}

/** The embedding page's origin: explicit X-Embed-Host header, else the referer URL. */
export function embedHostOf(req: Request): string | null {
  const header = req.headers.get("x-embed-host")?.trim();
  if (header) return header;
  return req.headers.get("referer") ?? req.headers.get("referrer");
}

export function isEmbedReferer(req: Request): boolean {
  const ref = req.headers.get("referer") ?? req.headers.get("referrer");
  if (!ref) return false;
  try {
    return new URL(ref).pathname.includes("/embed");
  } catch {
    return false;
  }
}

export function isEmbedAllowed(req: Request): boolean {
  if (process.env.DIGICHAT_EMBED_ENABLED === "1") return true;
  const token = req.headers.get("x-embed-token")?.trim();
  const expected = process.env.DIGICHAT_EMBED_TOKEN?.trim();
  return Boolean(expected && token === expected);
}

/** True when the request targets the unauthenticated /embed chat surface. */
export function isEmbedChatRequest(req: Request): boolean {
  const embedHost = req.headers.get("x-embed-host")?.trim();
  return Boolean(embedHost || isEmbedReferer(req));
}

/**
 * Resolves a registry tenant only when its own X-Embed-Token also matches.
 * A host string alone is never sufficient: it's the tenant's own public
 * domain, so registry membership by itself would let any caller claim any
 * tenant's config/backend routing (see #1339).
 */
export function resolveVerifiedEmbedTenant(req: Request): EmbedTenantConfig | null {
  const registered = resolveEmbedTenantByHost(embedHostOf(req));
  if (!registered) return null;
  const token = req.headers.get("x-embed-token")?.trim();
  return token && token === registered.token ? registered : null;
}

/** Resolve tenant for embed-only POST /api/chat (unauthenticated). */
export function resolveEmbedChatTenant(req: Request): EmbedChatTenantContext | Response {
  if (!isEmbedChatRequest(req)) {
    return new Response(JSON.stringify({ error: "not_embed_request" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }
  const registered = resolveVerifiedEmbedTenant(req);
  if (registered) {
    return {
      tenantSlug: registered.slug,
      ownerUserSub: "embed:anonymous",
      embedConfig: registered,
    };
  }
  if (isEmbedAllowed(req)) {
    return { tenantSlug: "embed", ownerUserSub: "embed:anonymous", embedConfig: null };
  }
  return new Response(
    JSON.stringify({
      error: "embed_disabled",
      message:
        "Embed chat requires DIGICHAT_EMBED_ENABLED=1 or a valid X-Embed-Token. See frontend/digichat/README.md.",
    }),
    { status: 503, headers: { "content-type": "application/json" } }
  );
}
