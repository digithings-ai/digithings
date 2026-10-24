/**
 * Plan tier and Stripe price mapping — a port of
 * `digiquant/supabase/functions/_shared/tiers.ts`.
 *
 * `loadPriceTierEnv` took an injectable `getEnv` in the edge version too; the
 * port passes the worker `env` record. The one behavioural difference is that
 * a default is no longer silently Deno — an unset binding now reads as `""`
 * exactly as before, and `pickPriceId` still returns `""` so the route can
 * raise the same `PRICE_NOT_CONFIGURED` error naming the same env var.
 */

import { envGet, type BillingEnv } from "./env";

export type PlanTier = "free" | "brief" | "desk" | "studio" | "enterprise";
export type PaidTier = Extract<PlanTier, "brief" | "desk" | "studio">;
export type SubscriptionStatus = "none" | "active" | "past_due" | "canceled";
export type Interval = "monthly" | "annual";

export function mapStripeStatus(status: string): SubscriptionStatus {
  switch (status) {
    case "active":
    case "trialing":
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
  briefMonthly: string;
  briefAnnual: string;
  deskMonthly: string;
  deskAnnual: string;
  studioMonthly: string;
  studioAnnual: string;
}

export function loadPriceTierEnv(env: BillingEnv): PriceTierEnv {
  return {
    briefMonthly: envGet(env, "STRIPE_PRICE_BRIEF_MONTHLY") ?? "",
    briefAnnual: envGet(env, "STRIPE_PRICE_BRIEF_ANNUAL") ?? "",
    deskMonthly: envGet(env, "STRIPE_PRICE_DESK_MONTHLY") ?? "",
    deskAnnual: envGet(env, "STRIPE_PRICE_DESK_ANNUAL") ?? "",
    studioMonthly: envGet(env, "STRIPE_PRICE_STUDIO_MONTHLY") ?? "",
    studioAnnual: envGet(env, "STRIPE_PRICE_STUDIO_ANNUAL") ?? "",
  };
}

/** The env var name that must be set for a (tier, interval) pair. */
export function priceEnvKey(tier: PaidTier, interval: Interval): string {
  return `STRIPE_PRICE_${tier.toUpperCase()}_${interval.toUpperCase()}`;
}

function paidTierFromPrices(priceId: string, prices: PriceTierEnv): PaidTier | null {
  const tiers: PaidTier[] = ["brief", "desk", "studio"];
  for (const tier of tiers) {
    if (prices[`${tier}Monthly` as keyof PriceTierEnv] === priceId && priceId !== "") {
      return tier;
    }
    if (prices[`${tier}Annual` as keyof PriceTierEnv] === priceId && priceId !== "") {
      return tier;
    }
  }
  return null;
}

export function planTierFromPriceId(priceId: string | null | undefined, prices: PriceTierEnv): PlanTier {
  if (!priceId) return "free";
  const tier = paidTierFromPrices(priceId, prices);
  if (!tier) {
    console.warn("stripe price id not mapped to a plan_tier; defaulting to free", priceId);
    return "free";
  }
  return tier;
}

export function planTierForSubscriptionStatus(
  status: SubscriptionStatus,
  priceId: string | null | undefined,
  prices: PriceTierEnv,
): PlanTier {
  if (status === "active" || status === "past_due") return planTierFromPriceId(priceId, prices);
  return "free";
}

export function pickPriceId(
  tier: PaidTier,
  interval: Interval,
  prices: PriceTierEnv,
): string | null {
  return prices[`${tier}${interval === "annual" ? "Annual" : "Monthly"}` as keyof PriceTierEnv] ?? null;
}

export function extractSubscriptionPriceId(subscription: unknown): string | null {
  const items = (subscription as { items?: { data?: unknown[] } } | null | undefined)?.items?.data;
  const first = Array.isArray(items) ? (items[0] as { price?: { id?: unknown } } | undefined) : undefined;
  const priceId = first?.price?.id;
  return typeof priceId === "string" && priceId.length > 0 ? priceId : null;
}