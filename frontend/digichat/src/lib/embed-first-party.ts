import { normalizeEmbedHost, resolveEmbedTenantByHost } from "@/lib/embed-tenants";

/** Prod marketing hosts only — no *.pages.dev in Phase 3. */
export const FIRST_PARTY_EMBED_HOSTS: ReadonlySet<string> = new Set([
  "digithings.ai",
  "www.digithings.ai",
]);

/** Loopback hosts eligible for dev-only tokenless embed when registered. */
export const DEV_LOOPBACK_EMBED_HOSTS: ReadonlySet<string> = new Set([
  "localhost",
  "127.0.0.1",
  "[::1]",
]);

export function isDigichatDevelopment(): boolean {
  return process.env.NODE_ENV === "development";
}

/**
 * True when the embed host may skip X-Embed-Token: prod digithings.ai hosts, or
 * (development only) loopback hosts registered in DIGICHAT_EMBED_TENANTS.
 */
export function isFirstPartyEmbedHost(host: string | null | undefined): boolean {
  const normalized = normalizeEmbedHost(host);
  if (!normalized) return false;
  if (FIRST_PARTY_EMBED_HOSTS.has(normalized)) return true;
  if (
    isDigichatDevelopment() &&
    DEV_LOOPBACK_EMBED_HOSTS.has(normalized) &&
    resolveEmbedTenantByHost(normalized) !== null
  ) {
    return true;
  }
  return false;
}
