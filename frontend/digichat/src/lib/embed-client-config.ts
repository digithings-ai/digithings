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
import {
  resolveEmbedTenantByHost,
  type EmbedLlmAccess,
  type EmbedTenantConfig,
} from "@/lib/embed-tenants";

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
  layout?: "page" | "embed";
  llmAccess?: EmbedLlmAccess;
  showLanguageSelector?: boolean;
  /** Tenant allows opt-in web search UI (#3420). Default false. */
  webSearch?: boolean;
  /**
   * Discriminator only — never project Foundry endpoints / digigraph URLs.
   * DigiChatSession uses this to enable regenerate/edit when the BFF turn
   * mutation API is available (#3475).
   */
  backendType?: "digigraph" | "foundry";
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
  layout: "embed",
  showLanguageSelector: false,
  webSearch: false,
};

/** Registry entry → client-safe config. Copies declared fields only; `token`
 *  and backend secrets (endpoints, agent names) have no branch here. The
 *  `backendType` discriminator is projected so the UI can enable Foundry-safe
 *  chrome (regen/edit) without learning relay URLs (#3475). */
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
    layout: cfg.layout ?? "embed",
    llmAccess: cfg.llmAccess,
    // Default ON for any real, registered tenant — the opposite default from
    // showByok, by product decision (#2103). DEFAULT_EMBED_TENANT_CONFIG
    // above (the unresolved/gated fallback) stays false.
    showLanguageSelector: cfg.showLanguageSelector ?? true,
    // Default OFF — corpus-only until tenant + user both opt in (#3420).
    webSearch: cfg.webSearch === true,
    backendType: cfg.backend.type,
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
  const trimmedToken = token?.trim();
  return trimmedToken && trimmedToken === registered.token
    ? toEmbedClientConfig(registered)
    : DEFAULT_EMBED_TENANT_CONFIG;
}

/**
 * Resolve the embed host for server render: explicit `?host=` first, else the
 * request referer origin — mirrors `resolveEmbedHost()` on the client (#2006).
 */
export function resolveEmbedHostParamOrReferer(
  host: string | undefined,
  referer: string | null | undefined,
): string | undefined {
  const explicit = host?.trim();
  if (explicit) return explicit;
  const ref = referer?.trim();
  if (!ref) return undefined;
  try {
    return new URL(ref).origin;
  } catch {
    return undefined;
  }
}
