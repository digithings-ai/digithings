/**
 * Legacy generic anonymous embed flag forwarded to the digichat container.
 *
 * The container reads `DIGICHAT_LEGACY_EMBED_ENABLED` (documented, preferred)
 * and its deprecated alias `DIGICHAT_EMBED_ENABLED` — either set to "1" opts in.
 * This helper applies the same OR semantics in the Worker so the documented
 * variable actually works on the Cloudflare path too.
 *
 * It must stay OFF unless an operator explicitly sets one to "1". Forwarding a
 * stock default of "1" turns the embed into an open relay for unregistered
 * hosts — a stock deploy would then grant
 * `{slug:"embed", ownerUserSub:"embed:anonymous"}`.
 */
export function legacyEmbedEnabledValue(
  legacy: string | undefined,
  deprecated: string | undefined,
): string {
  return legacy === "1" || deprecated === "1" ? "1" : "0";
}
