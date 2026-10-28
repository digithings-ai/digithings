import { normalizeEmbedHost } from "@/lib/embed-tenants";

/**
 * Hosts served only through a private invite link (DIG-1210). Without the
 * tenant's valid invite token the embed answers the standard 404, never the
 * generic turn-limited chat.
 */
export const INVITE_ONLY_EMBED_HOSTS: ReadonlyMap<string, string> = new Map([
  ["occ.digithings.ai", "occ"],
]);

/** True when `host` is invite-only and the resolved tenant is not that host's tenant. */
export function inviteRequiredButMissing(
  host: string | null | undefined,
  resolvedSlug: string | null | undefined,
): boolean {
  const normalized = normalizeEmbedHost(host);
  if (!normalized) return false;
  const slug = INVITE_ONLY_EMBED_HOSTS.get(normalized);
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
  const normalized = normalizeEmbedHost(host);
  if (normalized && INVITE_ONLY_EMBED_HOSTS.has(normalized)) return true;
  if (!slug) return false;
  for (const owner of INVITE_ONLY_EMBED_HOSTS.values()) {
    if (owner === slug) return true;
  }
  return false;
}
