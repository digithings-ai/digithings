/**
 * Desk+ gate reads `user.app_metadata.plan_tier`. Auth.js does not copy IdP
 * claims onto that field, so the OIDC `profile` callback has to.
 */
export function planTierFromOidcClaims(profile: Record<string, unknown>): string | undefined {
  const meta = profile.app_metadata;
  const fromMeta =
    meta && typeof meta === "object" && !Array.isArray(meta)
      ? (meta as { plan_tier?: unknown }).plan_tier
      : undefined;
  const raw = typeof fromMeta === "string" ? fromMeta : profile.plan_tier;
  if (typeof raw !== "string") return undefined;
  const tier = raw.trim();
  return tier || undefined;
}
