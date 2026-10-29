/**
 * Legacy tenant defaults — one release only.
 *
 * TODO(P-exit): delete this file once the live gated tenant's document
 * carries `chrome.slug`, `chrome.productChat`, `chrome.suggestions`,
 * `models.allowPicker` and `access`. Until then every reader takes the
 * document field first and falls back to these values, so the live tenant's
 * behaviour stays byte-identical. Nothing new may be added here.
 */

/** The embed host the gated tenant is served on today. */
export const LEGACY_GATED_TENANT_HOST = "occ.digithings.ai";

/** The tenant slug of the same row. */
export const LEGACY_GATED_TENANT_SLUG = "occ";

/** Seed of the R0-side gated list (`gatedTenantClaims`). */
export const LEGACY_GATED_TENANTS: ReadonlyArray<{
  slug: string;
  chatSlug: string;
  host: string;
}> = [
  {
    slug: LEGACY_GATED_TENANT_SLUG,
    chatSlug: LEGACY_GATED_TENANT_SLUG,
    host: LEGACY_GATED_TENANT_HOST,
  },
];
