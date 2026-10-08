import { normalizeEmbedHost, resolveEmbedTenantByHost } from "@/lib/embed-tenants";

/** Prod marketing / virtual first-party hosts only — no *.pages.dev in Phase 3. */
export const FIRST_PARTY_EMBED_HOSTS: ReadonlySet<string> = new Set([
  "digithings.ai",
  "www.digithings.ai",
  /**
   * Virtual host for digithings.ai/chat/occ (no DNS; iframe ?host= only).
   *
   * TODO(DIG-1210): remove. OCC is a client tenant with customer PII behind it,
   * and tokenless first-party access is what made its corpus reachable by any
   * visitor. It is being gated by an invite key instead — the Pages shell already
   * forwards `?token=` on /chat/occ (see apps/digithings-web/lib/inviteToken.ts),
   * and digichat already enforces `token` via X-Embed-Token. Deleting this entry
   * is the whole switch, and is deliberately a separate deploy from the key
   * rollout: land the token in DIGICHAT_EMBED_TENANTS first, or you lock OCC out.
   */
  "occ.digithings.ai",
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
 * True when the embed host is on the first-party allowlist: prod digithings.ai
 * hosts, or (development only) loopback hosts registered in
 * DIGICHAT_EMBED_TENANTS.
 *
 * This predicate is only half of a first-party tokenless decision. Callers must
 * also check a browser-attested origin (`embedOriginHostOf`) so the spoofable
 * `X-Embed-Host` header can never unlock a tenant by itself (see
 * `hostTenantAuthorized` in embed-chat-tenant.ts).
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
