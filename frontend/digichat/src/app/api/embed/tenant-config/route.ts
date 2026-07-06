import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";

/** Client-safe embed tenant config. Backend config (relay URLs) never leaves the server. */
export async function GET(req: Request): Promise<Response> {
  const cfg = resolveVerifiedEmbedTenant(req);
  const body = cfg
    ? {
        slug: cfg.slug,
        gateMode: cfg.gateMode,
        theme: cfg.theme,
        accent: cfg.accent ?? null,
        title: cfg.title ?? null,
        attribution: cfg.attribution,
      }
    : {
        slug: "embed",
        gateMode: "turn_limited",
        theme: "dark",
        accent: null,
        title: null,
        attribution: false,
      };
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
