/**
 * The client-safe projection of an embed tenant, and the two ways to obtain it.
 *
 * This shape is what both `GET /api/embed/tenant-config` and the `/embed`
 * server component hand to the browser. It is deliberately the SAME projection
 * in both places: the server component renders the first paint from it and the
 * hook then re-fetches the route to stay current, so any drift between the two
 * would reintroduce exactly the flash this module exists to remove.
 *
 * Backend config (relay URLs, digivault env refs) and the tenant `token` are
 * never part of it — see toEmbedClientConfig, which copies declared fields only.
 */

import { isFirstPartyEmbedHost } from "@/lib/embed-first-party";
import { getTenantSuggestionPool } from "@/lib/embed-suggestion-pools";
import { resolveEmbedTenantByHost, type EmbedTenantConfig } from "@/lib/embed-tenants";

export type EmbedTenantClientConfig = {
  slug: string;
  gateMode: "turn_limited" | "ungated" | "trial_form";
  theme: "dark" | "light";
  accent: { color: string; foreground: string } | null;
  attribution: boolean;
  title?: string;
  welcome?: string;
  suggestions?: string[];
  placeholder?: string;
  lockedContact?: string;
  showByok?: boolean;
  showStatusBar?: boolean;
  layout?: "page" | "embed";
};

/** Legacy defaults — deliberately the *gated* configuration, so a slow or
 * failed config fetch can only be more restrictive than intended, never less. */
export const DEFAULT_EMBED_TENANT_CONFIG: EmbedTenantClientConfig = {
  slug: "embed",
  gateMode: "turn_limited",
  theme: "dark",
  accent: null,
  attribution: false,
  showByok: false,
  showStatusBar: false,
  layout: "embed",
};

/** Registry entry → client-safe config. Copies declared fields only; `token`
 *  and `backend` have no branch here and so can never be projected. */
export function toEmbedClientConfig(cfg: EmbedTenantConfig): EmbedTenantClientConfig {
  return {
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
    showByok: cfg.showByok ?? false,
    showStatusBar: cfg.showStatusBar ?? false,
    layout: cfg.layout ?? "embed",
  };
}

/**
 * Resolves a tenant from the `/embed` URL's own `?token=` / `?host=` params,
 * for the server render that happens before any client fetch can.
 *
 * The header-driven counterpart is resolveVerifiedEmbedTenant() in
 * embed-chat-tenant.ts; the authorization rule here is deliberately identical
 * to it — a registered host alone is never enough for a customer tenant, only
 * the matching per-tenant token unlocks the real config (#1339) — because this
 * path discloses the same fields to the same anonymous visitor. An unknown host
 * or a wrong/absent token yields the gated defaults, never a partial tenant.
 */
export function resolveEmbedClientConfigFromParams(
  token: string | undefined,
  host: string | undefined,
): EmbedTenantClientConfig {
  const registered = resolveEmbedTenantByHost(host);
  if (!registered) return DEFAULT_EMBED_TENANT_CONFIG;
  if (isFirstPartyEmbedHost(host)) return toEmbedClientConfig(registered);
  return token && token === registered.token
    ? toEmbedClientConfig(registered)
    : DEFAULT_EMBED_TENANT_CONFIG;
}
