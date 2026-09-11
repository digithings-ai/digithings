/**
 * Legacy generic anonymous embed flag forwarded to the digichat container
 * (`DIGICHAT_EMBED_ENABLED`, deprecated alias of `DIGICHAT_LEGACY_EMBED_ENABLED`).
 *
 * It must stay OFF unless an operator explicitly sets it to "1". Forwarding a
 * stock default of "1" turns the embed into an open relay for unregistered
 * hosts — a stock deploy would then grant `{slug:"embed", ownerUserSub:"embed:anonymous"}`.
 */
export function legacyEmbedEnabledValue(raw: string | undefined): string {
  return raw === "1" ? "1" : "0";
}
