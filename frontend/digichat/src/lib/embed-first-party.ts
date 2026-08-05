import { normalizeEmbedHost } from "@/lib/embed-tenants";

/** Prod marketing hosts only — no *.pages.dev in Phase 3. */
export const FIRST_PARTY_EMBED_HOSTS: ReadonlySet<string> = new Set([
  "digithings.ai",
  "www.digithings.ai",
]);

export function isFirstPartyEmbedHost(host: string | null | undefined): boolean {
  const normalized = normalizeEmbedHost(host);
  return normalized !== null && FIRST_PARTY_EMBED_HOSTS.has(normalized);
}
