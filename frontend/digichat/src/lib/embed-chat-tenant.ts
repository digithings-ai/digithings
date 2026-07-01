import type { ChatTenantContext } from "@/lib/chat-route-context";

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

/** Resolve tenant for embed-only POST /api/chat (unauthenticated). */
export function resolveEmbedChatTenant(req: Request): ChatTenantContext | Response {
  if (!isEmbedChatRequest(req)) {
    return new Response(JSON.stringify({ error: "not_embed_request" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });
  }
  if (isEmbedAllowed(req)) {
    return { tenantSlug: "embed", ownerUserSub: "embed:anonymous" };
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
