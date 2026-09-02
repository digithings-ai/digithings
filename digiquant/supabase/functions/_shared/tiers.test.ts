/**
 * Unit tests for _shared/tiers.ts (no I/O).
 */

import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  extractSubscriptionPriceId,
  loadPriceTierEnv,
  mapStripeStatus,
  pickPriceId,
  planTierForSubscriptionStatus,
  planTierFromPriceId,
  priceEnvKey,
} from "./tiers.ts";

Deno.test("loadPriceTierEnv reads Deno.env keys", () => {
  Deno.env.set("STRIPE_PRICE_BRIEF_MONTHLY", "bm");
  Deno.env.set("STRIPE_PRICE_BRIEF_ANNUAL", "ba");
  Deno.env.set("STRIPE_PRICE_DESK_MONTHLY", "dm");
  Deno.env.set("STRIPE_PRICE_DESK_ANNUAL", "da");
  Deno.env.set("STRIPE_PRICE_STUDIO_MONTHLY", "sm");
  Deno.env.set("STRIPE_PRICE_STUDIO_ANNUAL", "sa");
  const prices = loadPriceTierEnv();
  assertEquals(prices.briefMonthly, "bm");
  assertEquals(prices.studioAnnual, "sa");
});

Deno.test("extractSubscriptionPriceId reads items.data[0]", () => {
  assertEquals(
    extractSubscriptionPriceId({
      items: { data: [{ price: { id: "price_x" } }] },
    }),
    "price_x",
  );
  assertEquals(extractSubscriptionPriceId({}), null);
});

Deno.test("mapStripeStatus unpaid → past_due", () => {
  assertEquals(mapStripeStatus("unpaid"), "past_due");
  assertEquals(mapStripeStatus("incomplete"), "none");
});

Deno.test("planTierFromPriceId with empty env is free", () => {
  assertEquals(
    planTierFromPriceId("price_anything", {
      briefMonthly: "",
      briefAnnual: "",
      deskMonthly: "",
      deskAnnual: "",
      studioMonthly: "",
      studioAnnual: "",
    }),
    "free",
  );
});

Deno.test("planTierForSubscriptionStatus gates paid tiers", () => {
  const prices = {
    briefMonthly: "bm",
    briefAnnual: "ba",
    deskMonthly: "dm",
    deskAnnual: "da",
    studioMonthly: "sm",
    studioAnnual: "sa",
  };
  assertEquals(planTierForSubscriptionStatus("none", "bm", prices), "free");
  assertEquals(planTierForSubscriptionStatus("canceled", "bm", prices), "free");
  assertEquals(planTierForSubscriptionStatus("active", "bm", prices), "brief");
  assertEquals(planTierForSubscriptionStatus("past_due", "sm", prices), "studio");
  assertEquals(planTierForSubscriptionStatus("active", "dm", prices), "desk");
});

Deno.test("priceEnvKey names Stripe price secrets for Checkout errors", () => {
  assertEquals(priceEnvKey("brief", "monthly"), "STRIPE_PRICE_BRIEF_MONTHLY");
  assertEquals(priceEnvKey("brief", "annual"), "STRIPE_PRICE_BRIEF_ANNUAL");
  assertEquals(priceEnvKey("desk", "monthly"), "STRIPE_PRICE_DESK_MONTHLY");
  assertEquals(priceEnvKey("desk", "annual"), "STRIPE_PRICE_DESK_ANNUAL");
  assertEquals(priceEnvKey("studio", "monthly"), "STRIPE_PRICE_STUDIO_MONTHLY");
  assertEquals(priceEnvKey("studio", "annual"), "STRIPE_PRICE_STUDIO_ANNUAL");
});

Deno.test("pickPriceId selects the env-backed price", () => {
  const prices = {
    briefMonthly: "bm",
    briefAnnual: "ba",
    deskMonthly: "dm",
    deskAnnual: "da",
    studioMonthly: "sm",
    studioAnnual: "sa",
  };
  assertEquals(pickPriceId("brief", "monthly", prices), "bm");
  assertEquals(pickPriceId("desk", "annual", prices), "da");
  assertEquals(pickPriceId("studio", "monthly", prices), "sm");
});
