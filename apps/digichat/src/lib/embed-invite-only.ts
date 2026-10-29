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
