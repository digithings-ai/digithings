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
import {
  BASELINE_EMBED_PLACEHOLDER,
  BASELINE_EMBED_SKIN,
  BASELINE_EMBED_SUGGESTIONS,
  BASELINE_EMBED_WELCOME,
  BASELINE_EMBED_WELCOME_BODY,
} from "@/lib/baseline-embed";
import { defaultThreadSkinForTenant, type ThreadSkin } from "@/lib/thread-skins";

export type EmbedTenantClientConfig = {
  slug: string;
  gateMode: "turn_limited" | "ungated" | "trial_form";
  theme: "dark" | "light";
  /** assistant-ui Thread layout. See thread-skins.ts */
  skin?: ThreadSkin;
  accent: { color: string; foreground: string } | null;
  attribution: boolean;
  title?: string;
  welcome?: string;
  welcomeBody?: string[];
  suggestions?: string[];
  placeholder?: string;
  /** User file picker. JSON omit / unresolved-tenant omit stays off except DEFAULT. */
  attachments?: boolean;
  lockedContact?: string;
  showByok?: boolean;
  layout?: "page" | "embed";
  llmAccess?: EmbedLlmAccess;
  showLanguageSelector?: boolean;
  /** Tenant allows opt-in web search UI (#3420). Default false. */
  webSearch?: boolean;
  /** Catalog entries — no MCP URLs */
  tools?: { catalog: Array<{ id: string; default?: boolean; label?: string }> };
  /** Operator MCP ids/labels only */
  mcp?: {
    servers: Array<{ id: string; label?: string; default?: boolean }>;
    allowUserServers?: boolean;
    allowAddForm?: boolean;
  };
  models?: { default?: string; available?: string[]; allowPicker?: boolean };
  /**
   * Discriminator only — never project Foundry endpoints / digigraph URLs.
   * CliThread uses this to enable regenerate/edit when the BFF turn
   * mutation API is available (#3475).
   */
  backendType?: "digigraph" | "foundry";
};

/**
 * Unresolved host / wrong token / no-host `/embed`. Looks like an unconfigured
 * digichat container (first-party skin, generic copy, attach+send) — never a
 * tenant brand. Gate stays turn-limited so a slow fetch cannot open a
 * trial_form / ungated tenant by accident.
 */
export const DEFAULT_EMBED_TENANT_CONFIG: EmbedTenantClientConfig = {
  slug: "embed",
  gateMode: "turn_limited",
  theme: "dark",
  skin: BASELINE_EMBED_SKIN,
  accent: null,
  attribution: false,
  welcome: BASELINE_EMBED_WELCOME,
  welcomeBody: [...BASELINE_EMBED_WELCOME_BODY],
  placeholder: BASELINE_EMBED_PLACEHOLDER,
  suggestions: [...BASELINE_EMBED_SUGGESTIONS],
  attachments: true,
  showByok: true,
  layout: "embed",
  showLanguageSelector: false,
  webSearch: true,
  // Baseline operator surface: no pinned servers, but the user-server form is
  // open (same as the deploy-path default). The bridge projects this with
  // strict ===true passthroughs, so the keys must be present here.
  mcp: { servers: [], allowUserServers: true, allowAddForm: true },
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
    skin: cfg.skin ?? defaultThreadSkinForTenant({ slug: cfg.slug }),
    accent: cfg.accent ?? null,
    attribution: cfg.attribution,
    title: cfg.title,
    welcome: cfg.welcome,
    welcomeBody: cfg.welcomeBody?.length ? cfg.welcomeBody : undefined,
    suggestions: cfg.suggestions ?? getTenantSuggestionPool(cfg.slug),
    placeholder: cfg.placeholder,
    lockedContact: cfg.lockedContact,
    attachments: cfg.attachments === true,
    showByok: cfg.showByok ?? false,
    layout: cfg.layout ?? "embed",
    llmAccess: cfg.llmAccess,
    // Default ON for any real, registered tenant — the opposite default from
    // showByok, by product decision (#2103). DEFAULT_EMBED_TENANT_CONFIG
    // above (the unresolved/gated fallback) stays false.
    showLanguageSelector: cfg.showLanguageSelector ?? true,
    // Tenant-gated default-on (#3420, #3859): omit/false stays corpus-only;
    // an enabled tenant pairs with the default-on user pref before digichat
    // sends X-Digi-Enable-Web-Search.
    webSearch: cfg.webSearch === true,
    tools: cfg.tools,
    mcp: cfg.mcp
      ? {
          servers: cfg.mcp.servers.map((s) => ({
            id: s.id,
            ...(s.label ? { label: s.label } : {}),
            ...(typeof s.default === "boolean" ? { default: s.default } : {}),
          })),
          allowUserServers: cfg.mcp.allowUserServers === true,
          allowAddForm: cfg.mcp.allowUserServers === true && cfg.mcp.allowAddForm === true,
        }
      : undefined,
    models: cfg.models,
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
 * path discloses the same fields to the same anonymous visitor. A first-party
 * host additionally needs a first-party `originHost` (browser-attested
 * `Origin`/`Referer`), never `?host=` alone. An unknown host or a wrong/absent
 * token yields the baseline defaults, never a partial tenant.
 */
export function resolveEmbedClientConfigFromParams(
  token: string | undefined,
  host: string | undefined,
  originHost?: string | null,
): EmbedTenantClientConfig {
  const registered = resolveEmbedTenantByHost(host);
  if (!registered) return DEFAULT_EMBED_TENANT_CONFIG;
  const trimmedToken = token?.trim();
  if (trimmedToken && trimmedToken === registered.token) {
    return toEmbedClientConfig(registered);
  }
  // First-party tokenless paint requires a first-party browser-attested origin
  // too — `?host=`/`X-Embed-Host` alone is display-only and must not unlock it.
  if (isFirstPartyEmbedHost(host) && isFirstPartyEmbedHost(originHost)) {
    return toEmbedClientConfig(registered);
  }
  return DEFAULT_EMBED_TENANT_CONFIG;
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
