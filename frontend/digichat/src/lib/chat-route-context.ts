import type { DigiChatAuthContext } from "@/lib/request-auth";

export type ChatTenantContext = {
  tenantSlug: string;
  ownerUserSub: string;
};

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

/** Resolve tenant + owner for POST /api/chat (SIMP-027). */
export async function resolveChatTenantContext(
  req: Request,
  authResult: DigiChatAuthContext | Response
): Promise<ChatTenantContext | Response> {
  const embedFromReferer = isEmbedReferer(req);
  const embedHost =
    req.headers.get("x-embed-host")?.trim() || (embedFromReferer ? "referer" : undefined);

  if (authResult instanceof Response) {
    if (embedHost && isEmbedAllowed(req)) {
      return { tenantSlug: "embed", ownerUserSub: "embed:anonymous" };
    }
    if (embedHost) {
      return new Response(
        JSON.stringify({
          error: "embed_disabled",
          message:
            "Embed chat requires DIGICHAT_EMBED_ENABLED=1 or a valid X-Embed-Token. See frontend/digichat/README.md.",
        }),
        { status: 503, headers: { "content-type": "application/json" } }
      );
    }
    return authResult;
  }

  return {
    tenantSlug: authResult.tenantSlug,
    ownerUserSub: authResult.ownerUserSub,
  };
}
