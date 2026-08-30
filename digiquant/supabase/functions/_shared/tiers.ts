/**
 * Stripe price-id → Olympus consumer plan_tier mapping (T2 / spec D1).
 *
 * Consumer tiers here are `free | baseline | custom | enterprise` — NOT ADR-0004's
 * metered API seat names. Enterprise is invoice-only (no self-serve price id).
 *
 * Price ids come from Deno.env (set via `supabase secrets set`); never hard-code.
 */

export type PlanTier = "free" | "baseline" | "custom" | "enterprise";

export type SubscriptionStatus = "none" | "active" | "past_due" | "canceled";

/** Stripe subscription.status → workspaces.subscription_status CHECK values. */
export function mapStripeStatus(status: string | null | undefined): SubscriptionStatus {
  switch (status) {
    case "active":
    case "trialing":
      // Schema CHECK has no `trialing`; trial grants the same gate as active.
      return "active";
    case "past_due":
    case "unpaid":
      return "past_due";
    case "canceled":
    case "incomplete_expired":
      return "canceled";
    case "incomplete":
    case "paused":
    default:
      return "none";
  }
}

export interface PriceTierEnv {
  baselineMonthly: string;
  baselineAnnual: string;
  customMonthly: string;
  customAnnual: string;
}

export function loadPriceTierEnv(
  getEnv: (key: string) => string | undefined = (k) => Deno.env.get(k),
): PriceTierEnv {
  return {
    baselineMonthly: getEnv("STRIPE_PRICE_BASELINE_MONTHLY") ?? "",
    baselineAnnual: getEnv("STRIPE_PRICE_BASELINE_ANNUAL") ?? "",
    customMonthly: getEnv("STRIPE_PRICE_CUSTOM_MONTHLY") ?? "",
    customAnnual: getEnv("STRIPE_PRICE_CUSTOM_ANNUAL") ?? "",
  };
}

/**
 * Map a Stripe Price id to plan_tier. Unknown / empty ⇒ `free` (safe downgrade).
 * Deleted/canceled subscriptions must call this with null / use `free` directly.
 */
export function planTierFromPriceId(
  priceId: string | null | undefined,
  prices: PriceTierEnv = loadPriceTierEnv(),
): PlanTier {
  if (!priceId) return "free";
  const {
    baselineMonthly,
    baselineAnnual,
    customMonthly,
    customAnnual,
  } = prices;
  if (
    (baselineMonthly && priceId === baselineMonthly) ||
    (baselineAnnual && priceId === baselineAnnual)
  ) {
    return "baseline";
  }
  if (
    (customMonthly && priceId === customMonthly) ||
    (customAnnual && priceId === customAnnual)
  ) {
    return "custom";
  }
  return "free";
}

/** First price id on a Stripe Subscription-like object (items.data[0].price.id). */
export function extractSubscriptionPriceId(subscription: {
  items?: { data?: Array<{ price?: { id?: string } }> };
}): string | null {
  const id = subscription.items?.data?.[0]?.price?.id;
  return typeof id === "string" && id.length > 0 ? id : null;
}
