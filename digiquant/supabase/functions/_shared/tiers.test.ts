/**
 * Unit tests for _shared/tiers.ts (no I/O).
 */

import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  extractSubscriptionPriceId,
  loadPriceTierEnv,
  mapStripeStatus,
  planTierForSubscriptionStatus,
  planTierFromPriceId,
} from "./tiers.ts";

Deno.test("loadPriceTierEnv reads Deno.env keys", () => {
  Deno.env.set("STRIPE_PRICE_BASELINE_MONTHLY", "bm");
  Deno.env.set("STRIPE_PRICE_BASELINE_ANNUAL", "ba");
  Deno.env.set("STRIPE_PRICE_CUSTOM_MONTHLY", "cm");
  Deno.env.set("STRIPE_PRICE_CUSTOM_ANNUAL", "ca");
  const prices = loadPriceTierEnv();
  assertEquals(prices.baselineMonthly, "bm");
  assertEquals(prices.customAnnual, "ca");
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
      baselineMonthly: "",
      baselineAnnual: "",
      customMonthly: "",
      customAnnual: "",
    }),
    "free",
  );
});

Deno.test("planTierForSubscriptionStatus gates paid tiers", () => {
  const prices = {
    baselineMonthly: "bm",
    baselineAnnual: "ba",
    customMonthly: "cm",
    customAnnual: "ca",
  };
  assertEquals(planTierForSubscriptionStatus("none", "bm", prices), "free");
  assertEquals(planTierForSubscriptionStatus("canceled", "bm", prices), "free");
  assertEquals(planTierForSubscriptionStatus("active", "bm", prices), "baseline");
  assertEquals(planTierForSubscriptionStatus("past_due", "cm", prices), "custom");
});
