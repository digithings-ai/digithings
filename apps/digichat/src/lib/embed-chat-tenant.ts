import type { ChatTenantContext } from "@/lib/chat-route-context";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  toEmbedClientConfig,
  type EmbedTenantClientConfig,
} from "@/lib/embed-client-config";
import { isFirstPartyEmbedHost } from "@/lib/embed-first-party";
import { isLegacyEmbedEnabled, LEGACY_EMBED_DISABLED_MESSAGE } from "@/lib/embed-legacy-gate";
import {
  hasConfiguredEmbedTenants,
  normalizeEmbedHost,
  resolveEmbedTenantByHost,
  type EmbedTenantConfig,
} from "@/lib/embed-tenants";
import {
  deploymentToEmbedTenant,
  getAnonymousClientInstall,
  getDigichatConfig,
  matchHostDeployment,
} from "@/lib/deploy-config/loader";

export type EmbedChatTenantContext = ChatTenantContext & {
  embedConfig: EmbedTenantConfig | null;
};

/** Extracts the embed config from either tenant context variant, or null when absent. */
export function embedConfigOf(
  ctx: ChatTenantContext | EmbedChatTenantContext
): EmbedTenantConfig | null {
  return "embedConfig" in ctx ? ctx.embedConfig : null;
}

/**
 * The embedding page's claimed host: explicit `X-Embed-Host` header, else the
 * referer URL. **Selection only, never authorization** — the header is
 * client-supplied, so it may pick which tenant config to consider but can never
 * by itself unlock a tokenless/first-party tenant (see `embedOriginHostOf`).
 */
export function embedHostOf(req: Request): string | null {
  const header = req.headers.get("x-embed-host")?.trim();
  if (header) return header;
  return req.headers.get("referer") ?? req.headers.get("referrer");
}

/** Minimal header accessor shared by `Request` and Next's `ReadonlyHeaders`. */
export type HeaderReader = { get(name: string): string | null | undefined };

/**
 * The browser-attested request origin host: `Origin` first, else the `Referer`
 * host. Both are forbidden header names — page JavaScript cannot set them — so
 * unlike `X-Embed-Host` this may back a first-party (tokenless) decision. It is
 * still not a cryptographic proof: a non-browser caller can send any header, so
 * per-tenant tokens remain the strongest authorization.
 */
export function embedOriginHostOf(reader: HeaderReader): string | null {
  const origin = reader.get("origin")?.trim();
  if (origin) return normalizeEmbedHost(origin);
  const ref = reader.get("referer") ?? reader.get("referrer");
  if (!ref?.trim()) return null;
  return normalizeEmbedHost(ref);
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
  if (isLegacyEmbedEnabled()) return true;
  const token = req.headers.get("x-embed-token")?.trim();
  const expected = process.env.DIGICHAT_EMBED_TOKEN?.trim();
  return Boolean(expected && token === expected);
}

/** True when the request targets the unauthenticated /embed chat surface. */
export function isEmbedChatRequest(req: Request): boolean {
  const embedHost = req.headers.get("x-embed-host")?.trim();
  return Boolean(embedHost || isEmbedReferer(req));
}

/** Token match for a tenant whose registry entry carries a non-empty secret. */
function tokenMatches(required: string, token: string | null | undefined): boolean {
  const expected = required.trim();
  const presented = token?.trim();
  return Boolean(expected && presented && presented === expected);
}

/**
 * Authorizes a host/registry tenant. Two acceptable proofs:
 *  1. the tenant's own `X-Embed-Token` matches (strongest), or
 *  2. the selected host AND the browser-attested request origin are both on the
 *     first-party allowlist.
 * `X-Embed-Host` alone is never sufficient: customer hosts always need a token,
 * and first-party hosts need a first-party origin (not the spoofable header).
 */
function hostTenantAuthorized(
  tenant: EmbedTenantConfig,
  token: string | null | undefined,
  host: string | null | undefined,
  originHost: string | null | undefined,
): boolean {
  if (tokenMatches(tenant.token, token)) return true;
  return isFirstPartyEmbedHost(host) && isFirstPartyEmbedHost(originHost);
}

/**
 * Authorizes the single-install YAML `deployment` (client container). An empty
 * configured token means "this container exists only for this client", so any
 * parent may use it — the operator chose a dedicated install. Callers still gate
 * this on `hasConfiguredEmbedTenants()` so a multi-tenant deploy never falls
 * through to it.
 */
function installAuthorized(
  install: EmbedTenantConfig,
  token: string | null | undefined,
): boolean {
  const required = install.token.trim();
  if (!required) return true;
  return tokenMatches(required, token);
}

/**
 * Registry / YAML host wins (token / first-party rules, #1339). Canonical
 * lookup is `getDigichatConfig()` hosts (YAML + DIGICHAT_EMBED_TENANTS merge)
 * so product embed examples (`chrome.skin`, tools.catalog) actually paint.
 * JSON-only registry is a fallback when config load fails. If the host is
 * not registered, a client-container YAML `deployment` is the product —
 * that is how `DIGICHAT_CONFIG_PATH=.../skins/chatgpt.yaml` actually
 * mounts ChatGPT and talks to POST /api/chat, not just the docs.
 */
function tenantFromMergedHosts(
  host: string | null | undefined,
): EmbedTenantConfig | null {
  if (!host?.trim()) return null;
  try {
    const dep = matchHostDeployment(host, getDigichatConfig());
    return dep ? deploymentToEmbedTenant(dep) : null;
  } catch {
    return null;
  }
}

export function resolveVerifiedEmbedTenantFromHostToken(
  host: string | null | undefined,
  token: string | null | undefined,
  originHost?: string | null,
): EmbedTenantConfig | null {
  const tenant = tenantFromMergedHosts(host) ?? resolveEmbedTenantByHost(host);
  if (tenant) {
    return hostTenantAuthorized(tenant, token, host, originHost) ? tenant : null;
  }
  // No host match: only a single-install client container may serve an
  // unregistered parent — and never once a multi-tenant registry is configured.
  if (hasConfiguredEmbedTenants()) return null;
  const install = getAnonymousClientInstall();
  if (!install) return null;
  const asTenant = deploymentToEmbedTenant(install);
  return installAuthorized(asTenant, token) ? asTenant : null;
}

/**
 * Resolves a tenant when its own `X-Embed-Token` matches, or — for a
 * first-party host — when the request also carries a first-party
 * browser-attested origin (`Origin`/`Referer`). Customer hosts always require
 * a token; `X-Embed-Host` alone is never authorization (#1339, #1866).
 */
export function resolveVerifiedEmbedTenant(req: Request): EmbedTenantConfig | null {
  return resolveVerifiedEmbedTenantFromHostToken(
    embedHostOf(req),
    req.headers.get("x-embed-token"),
    embedOriginHostOf(req.headers),
  );
}

/**
 * First paint for `/embed` — same tenant as GET /api/embed/tenant-config.
 * `originHost` is the browser-attested origin host (see `embedOriginHostOf`);
 * the page passes it from the navigation request so first-party paint keeps
 * working without trusting the client-supplied `?host=`.
 */
export function resolveEmbedClientConfigForPaint(
  token: string | undefined,
  host: string | undefined,
  originHost?: string | null,
): EmbedTenantClientConfig {
  const cfg = resolveVerifiedEmbedTenantFromHostToken(host, token, originHost);
  return cfg ? toEmbedClientConfig(cfg) : DEFAULT_EMBED_TENANT_CONFIG;
}

/** Anonymous `chrome.mode: app` product on `/` (layout templates). */
export function resolveAnonymousInstallChat(): EmbedChatTenantContext | null {
  const install = getAnonymousClientInstall();
  if (!install) return null;
  return {
    tenantSlug: install.slug,
    ownerUserSub: "embed:anonymous",
    embedConfig: deploymentToEmbedTenant(install),
  };
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
  // Once tenants are configured, an unrecognized host is refused — never the
  // legacy generic anonymous fallback, even if the flag is set.
  if (!hasConfiguredEmbedTenants() && isEmbedAllowed(req)) {
    return { tenantSlug: "embed", ownerUserSub: "embed:anonymous", embedConfig: null };
  }
  return new Response(
    JSON.stringify({
      error: "embed_disabled",
      message: LEGACY_EMBED_DISABLED_MESSAGE,
    }),
    { status: 503, headers: { "content-type": "application/json" } }
  );
}
