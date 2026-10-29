import { normalizeEmbedHost } from "@/lib/embed-tenants";

/**
 * Hosts served only through a private invite link (DIG-1210). Without the
 * tenant's valid invite token the embed answers the standard 404, never the
 * generic turn-limited chat.
 */
export const INVITE_ONLY_EMBED_HOSTS: ReadonlyMap<string, string> = new Map([
  ["occ.digithings.ai", "occ"],
]);

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
  const slug = configuredInviteOnlyHosts().get(normalized);
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
  const hosts = configuredInviteOnlyHosts();
  if (normalized && hosts.has(normalized)) return true;
  if (!slug) return false;
  for (const owner of hosts.values()) {
    if (owner === slug) return true;
  }
  return false;
}
