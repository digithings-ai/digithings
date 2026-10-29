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

/**
 * TODO(P-exit): the product-chat settings the gated tenant's live row has
 * today, applied only to that row while it does not set `chrome.productChat`.
 * Every other product chat starts safe: premium meter on, tokens-per-minute
 * limit kept, no catalog picker unless `models.allowPicker: true`. When the
 * client repo writes the new fields it writes these values explicitly
 * (`models.premiumMeter: false`, `guardrails.tpmLimit: false`,
 * `models.allowPicker: true`) and this block goes.
 */
export const LEGACY_GATED_TENANT_PRODUCT_CHAT = {
  /** No premium meter. */
  premiumMeter: false,
  /** No tokens-per-minute limit. */
  tpmLimit: false,
  /** Catalog picker on unless the row writes `models.occPicker: false`. */
  picker: true,
} as const;
