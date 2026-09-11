import type { ChatTenantContext } from "@/lib/chat-route-context";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  toEmbedClientConfig,
  type EmbedTenantClientConfig,
} from "@/lib/embed-client-config";
import { isFirstPartyEmbedHost } from "@/lib/embed-first-party";
import { isLegacyEmbedEnabled, LEGACY_EMBED_DISABLED_MESSAGE } from "@/lib/embed-legacy-gate";
import { resolveEmbedTenantByHost, type EmbedTenantConfig } from "@/lib/embed-tenants";
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

function tokenUnlocksTenant(
  tenant: EmbedTenantConfig,
  token: string | null | undefined,
): boolean {
  const required = tenant.token.trim();
  if (!required) return true;
  const presented = token?.trim();
  return Boolean(presented && presented === required);
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
): EmbedTenantConfig | null {
  const fromConfig = tenantFromMergedHosts(host);
  if (fromConfig) {
    if (isFirstPartyEmbedHost(host)) return fromConfig;
    return tokenUnlocksTenant(fromConfig, token) ? fromConfig : null;
  }
  const registered = resolveEmbedTenantByHost(host);
  if (registered) {
    if (isFirstPartyEmbedHost(host)) return registered;
    return tokenUnlocksTenant(registered, token) ? registered : null;
  }
  const install = getAnonymousClientInstall();
  if (!install) return null;
  const asTenant = deploymentToEmbedTenant(install);
  return tokenUnlocksTenant(asTenant, token) ? asTenant : null;
}

/**
 * Resolves a registry tenant when first-party allowlisted (digithings.ai /
 * www) or when its own X-Embed-Token matches. Customer hosts still require
 * a token — host alone is never enough for them (#1339). First-party
 * bypass is Phase 3 (#1866).
 */
export function resolveVerifiedEmbedTenant(req: Request): EmbedTenantConfig | null {
  return resolveVerifiedEmbedTenantFromHostToken(
    embedHostOf(req),
    req.headers.get("x-embed-token"),
  );
}

/** First paint for `/embed` — same tenant as GET /api/embed/tenant-config. */
export function resolveEmbedClientConfigForPaint(
  token: string | undefined,
  host: string | undefined,
): EmbedTenantClientConfig {
  const cfg = resolveVerifiedEmbedTenantFromHostToken(host, token);
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
  if (isEmbedAllowed(req)) {
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
