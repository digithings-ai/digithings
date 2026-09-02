/**
 * Stripe price-id → digiquant consumer plan_tier mapping (T2 / PRICING.md).
 *
 * Consumer tiers: `free | brief | desk | studio | enterprise` — NOT ADR-0004's
 * metered API seat names. Enterprise is invoice-only (no self-serve price id).
 *
 * Price ids come from Deno.env (set via `supabase secrets set`); never hard-code.
 */

export type PlanTier = "free" | "brief" | "desk" | "studio" | "enterprise";

export type PaidTier = Extract<PlanTier, "brief" | "desk" | "studio">;

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

/**
 * Paid claim only while Stripe status maps to active / past_due
 * (covers trialing→active and unpaid→past_due). incomplete / canceled / none ⇒ free.
 */
export function planTierForSubscriptionStatus(
  status: SubscriptionStatus,
  priceId: string | null | undefined,
  prices?: PriceTierEnv,
): PlanTier {
  if (status === "active" || status === "past_due") {
    return planTierFromPriceId(priceId, prices);
  }
  return "free";
}

export interface PriceTierEnv {
  briefMonthly: string;
  briefAnnual: string;
  deskMonthly: string;
  deskAnnual: string;
  studioMonthly: string;
  studioAnnual: string;
}

export function loadPriceTierEnv(
  getEnv: (key: string) => string | undefined = (k) => Deno.env.get(k),
): PriceTierEnv {
  return {
    briefMonthly: getEnv("STRIPE_PRICE_BRIEF_MONTHLY") ?? "",
    briefAnnual: getEnv("STRIPE_PRICE_BRIEF_ANNUAL") ?? "",
    deskMonthly: getEnv("STRIPE_PRICE_DESK_MONTHLY") ?? "",
    deskAnnual: getEnv("STRIPE_PRICE_DESK_ANNUAL") ?? "",
    studioMonthly: getEnv("STRIPE_PRICE_STUDIO_MONTHLY") ?? "",
    studioAnnual: getEnv("STRIPE_PRICE_STUDIO_ANNUAL") ?? "",
  };
}

/** Env var name for a paid Checkout price — used in PRICE_NOT_CONFIGURED messages. */
export function priceEnvKey(tier: PaidTier, interval: "monthly" | "annual"): string {
  const stem = tier.toUpperCase();
  return interval === "monthly" ? `STRIPE_PRICE_${stem}_MONTHLY` : `STRIPE_PRICE_${stem}_ANNUAL`;
}

function paidTierFromPrices(priceId: string, prices: PriceTierEnv): PaidTier | null {
  const {
    briefMonthly,
    briefAnnual,
    deskMonthly,
    deskAnnual,
    studioMonthly,
    studioAnnual,
  } = prices;
  if ((briefMonthly && priceId === briefMonthly) || (briefAnnual && priceId === briefAnnual)) {
    return "brief";
  }
  if ((deskMonthly && priceId === deskMonthly) || (deskAnnual && priceId === deskAnnual)) {
    return "desk";
  }
  if (
    (studioMonthly && priceId === studioMonthly) ||
    (studioAnnual && priceId === studioAnnual)
  ) {
    return "studio";
  }
  return null;
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
  const mapped = paidTierFromPrices(priceId, prices);
  if (mapped) return mapped;
  console.warn("stripe price id not mapped to a plan_tier; defaulting to free", priceId);
  return "free";
}

export function pickPriceId(
  tier: PaidTier,
  interval: "monthly" | "annual",
  prices: PriceTierEnv,
): string {
  if (tier === "brief") {
    return interval === "monthly" ? prices.briefMonthly : prices.briefAnnual;
  }
  if (tier === "desk") {
    return interval === "monthly" ? prices.deskMonthly : prices.deskAnnual;
  }
  return interval === "monthly" ? prices.studioMonthly : prices.studioAnnual;
}

/** First price id on a Stripe Subscription-like object (items.data[0].price.id). */
export function extractSubscriptionPriceId(subscription: {
  items?: { data?: Array<{ price?: { id?: string } }> };
}): string | null {
  const id = subscription.items?.data?.[0]?.price?.id;
  return typeof id === "string" && id.length > 0 ? id : null;
}
