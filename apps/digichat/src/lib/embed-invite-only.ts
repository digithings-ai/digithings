import {
  getEmbedTenantRegistry,
  isGatedEmbedTenant,
  normalizeEmbedHost,
} from "@/lib/embed-tenants";
import { gatedTenantClaims } from "@/lib/deploy-config/tenant-chrome";

/**
 * Hosts served only through a private invite link (DIG-1210). Without the
 * tenant's valid invite token the embed answers the standard 404, never the
 * generic turn-limited chat.
 *
 * The gated hosts are recorded outside the tenant document: the R0-side
 * claims list (legacy seed + the last registry that parsed cleanly). A gated
 * registry row (`gateMode: "invite"` or an `access.invite` block) adds its
 * hosts. If the registry cannot be read, the claims alone still deny.
 */
export const INVITE_ONLY_EMBED_HOSTS: ReadonlyMap<string, string> = new Map(
  gatedTenantClaims()
    .filter((c): c is typeof c & { host: string } => Boolean(c.host))
    .map((c) => [c.host, c.slug]),
);

/** host → tenant slug for every gated host, claims first. Fails closed. */
function inviteOnlyHosts(): ReadonlyMap<string, string> {
  const out = new Map<string, string>();
  for (const claim of gatedTenantClaims()) {
    if (claim.host) out.set(claim.host, claim.slug);
  }
  // Hosts from DIGICHAT_INVITE_PAGES (the env, not the registry) also deny.
  for (const [h, sl] of configuredInviteOnlyHosts()) if (!out.has(h)) out.set(h, sl);
  let registry: ReturnType<typeof getEmbedTenantRegistry>;
  try {
    registry = getEmbedTenantRegistry();
  } catch {
    // Unreadable registry: the claims recorded outside it still deny.
    return out;
  }
  for (const [host, cfg] of registry) {
    if (isGatedEmbedTenant(cfg) && !out.has(host)) out.set(host, cfg.slug);
  }
  return out;
}

/**
 * Invite-only hosts beyond OCC, from the non-secret `DIGICHAT_INVITE_PAGES`
 * JSON the Worker forwards (`{"<slug>": {"host": "<host>", "keyEnv": "..."}}`,
 * see apps/digichat-cloudflare/src/invite-pages.ts). Only slug and host are
 * read here; the edge owns the keys. A malformed value adds nothing, and the
 * OCC entry above can never be removed by it.
 */
export function configuredInviteOnlyHosts(
  raw: string | undefined = process.env.DIGICHAT_INVITE_PAGES,
): Map<string, string> {
  const out = new Map(INVITE_ONLY_EMBED_HOSTS);
  const text = (raw ?? "").trim();
  if (!text) return out;
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return out;
    for (const [slug, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug)) continue;
      const host = normalizeEmbedHost((value as { host?: unknown } | null)?.host as string | undefined);
      if (host && !out.has(host)) out.set(host, slug);
    }
  } catch {
    /* not JSON: nothing beyond OCC */
  }
  return out;
}

/** True when `host` is invite-only and the resolved tenant is not that host's tenant. */
export function inviteRequiredButMissing(
  host: string | null | undefined,
  resolvedSlug: string | null | undefined,
): boolean {
  const normalized = normalizeEmbedHost(host);
  if (!normalized) return false;
  const slug = inviteOnlyHosts().get(normalized);
  if (!slug) return false;
  return resolvedSlug !== slug;
}

/**
 * True when `host` is invite-only, or `slug` is the tenant of an invite-only
 * host (an alias or a merged registry row must not reopen it). Such a
 * deployment is never served without its own invite token (DIG-3585).
 */
export function isInviteOnlyDeployment(
  host: string | null | undefined,
  slug: string | null | undefined,
): boolean {
  const hosts = inviteOnlyHosts();
  const normalized = normalizeEmbedHost(host);
  if (normalized && hosts.has(normalized)) return true;
  if (!slug) return false;
  for (const owner of hosts.values()) {
    if (owner === slug) return true;
  }
  return false;
}
