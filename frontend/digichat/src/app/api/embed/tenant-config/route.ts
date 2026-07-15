import { resolveVerifiedEmbedTenant } from "@/lib/embed-chat-tenant";
import { getTenantSuggestionPool } from "@/lib/embed-suggestion-pools";

/** Client-safe embed tenant config. Backend config (relay URLs) never leaves the server. */
export async function GET(req: Request): Promise<Response> {
  const cfg = resolveVerifiedEmbedTenant(req);
  const body = cfg
    ? {
        slug: cfg.slug,
        gateMode: cfg.gateMode,
        theme: cfg.theme,
        accent: cfg.accent ?? null,
        attribution: cfg.attribution,
        title: cfg.title,
        welcome: cfg.welcome,
        suggestions: cfg.suggestions ?? getTenantSuggestionPool(cfg.slug),
        placeholder: cfg.placeholder,
        lockedContact: cfg.lockedContact,
      }
    : { slug: "embed", gateMode: "turn_limited", theme: "dark", accent: null, attribution: false };
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
