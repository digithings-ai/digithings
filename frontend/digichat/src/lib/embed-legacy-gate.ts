/**
 * Legacy generic embed gate — opens /embed for *unregistered* hosts only.
 * Registered tenants use DIGICHAT_EMBED_TENANTS (token or first-party bypass).
 * Never default-on when tenants are configured (security).
 */

/** @deprecated Use DIGICHAT_LEGACY_EMBED_ENABLED — alias removed after one release. */
const LEGACY_EMBED_ENABLED_ENV = "DIGICHAT_EMBED_ENABLED";

export function isLegacyEmbedEnabled(): boolean {
  if (process.env.DIGICHAT_LEGACY_EMBED_ENABLED === "1") return true;
  return process.env[LEGACY_EMBED_ENABLED_ENV] === "1";
}

export const LEGACY_EMBED_DISABLED_MESSAGE =
  "Embed chat is not enabled for this host. Register it in DIGICHAT_EMBED_TENANTS " +
  "(with token or first-party bypass), or set DIGICHAT_LEGACY_EMBED_ENABLED=1 for " +
  "legacy generic embed on unregistered hosts. See frontend/digichat/README.md.";
