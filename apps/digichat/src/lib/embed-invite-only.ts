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
