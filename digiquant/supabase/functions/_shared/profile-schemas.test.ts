/**
 * Deno unit tests for InvestmentProfile / AssetPreferences schema re-validation.
 *
 * Covers the closed validator used by PATCH /profile — enum, pattern, integer
 * bounds, required fields, additionalProperties, and watchlist shape. A single
 * SCHEMA_INVALID handler test is not enough: bad payloads must fail closed
 * before olympus_profile_config writes.
 *
 *   deno test --allow-read _shared/profile-schemas.test.ts
 */

import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  HOUSE_PROFILE_KEY,
  validateAgainstSchema,
  validateAssetPreferences,
  validateInvestmentProfile,
} from "./profile-schemas.ts";

const validInvestment = {
  risk_tolerance: "moderate",
  horizon_years: 10,
  liquidity_needs: "medium",
  base_currency: "USD",
  tax_jurisdiction: "US",
  esg_preference: "none",
  experience_level: "intermediate",
};

Deno.test("validateInvestmentProfile accepts a complete v1 contract", () => {
  const result = validateInvestmentProfile({
    ...validInvestment,
    excluded_sectors: ["tobacco"],
    schema_version: 1,
  });
  assertEquals(result.ok, true);
});

Deno.test("validateInvestmentProfile rejects unknown enum values", () => {
  const result = validateInvestmentProfile({
    ...validInvestment,
    risk_tolerance: "yolo",
  });
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "risk_tolerance");
    assertEquals(
      result.errors[0]?.message.includes("must be one of:"),
      true,
    );
  }
});

Deno.test("validateInvestmentProfile rejects non-ISO base_currency", () => {
  const result = validateInvestmentProfile({
    ...validInvestment,
    base_currency: "usd",
  });
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "base_currency");
    assertEquals(result.errors[0]?.message.includes("must match"), true);
  }
});

Deno.test("validateInvestmentProfile rejects horizon_years outside 1..50", () => {
  const low = validateInvestmentProfile({ ...validInvestment, horizon_years: 0 });
  assertEquals(low.ok, false);
  if (!low.ok) {
    assertEquals(low.errors[0]?.path, "horizon_years");
    assertEquals(low.errors[0]?.message, "must be >= 1");
  }

  const high = validateInvestmentProfile({
    ...validInvestment,
    horizon_years: 51,
  });
  assertEquals(high.ok, false);
  if (!high.ok) {
    assertEquals(high.errors[0]?.path, "horizon_years");
    assertEquals(high.errors[0]?.message, "must be <= 50");
  }
});

Deno.test("validateInvestmentProfile rejects non-integer horizon_years", () => {
  const result = validateInvestmentProfile({
    ...validInvestment,
    horizon_years: 10.5,
  });
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "horizon_years");
    assertEquals(result.errors[0]?.message, "must be an integer");
  }
});

Deno.test("validateInvestmentProfile rejects missing required fields", () => {
  const result = validateInvestmentProfile({ risk_tolerance: "moderate" });
  assertEquals(result.ok, false);
  if (!result.ok) {
    const paths = new Set(result.errors.map((e) => e.path));
    assertEquals(paths.has("horizon_years"), true);
    assertEquals(paths.has("liquidity_needs"), true);
    assertEquals(paths.has("base_currency"), true);
    assertEquals(
      result.errors.every((e) => e.message === "required"),
      true,
    );
  }
});

Deno.test("validateInvestmentProfile rejects additional properties", () => {
  const result = validateInvestmentProfile({
    ...validInvestment,
    secret_field: "nope",
  });
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "secret_field");
    assertEquals(result.errors[0]?.message, "additional property not allowed");
  }
});

Deno.test("validateInvestmentProfile rejects non-object roots", () => {
  for (const value of [null, "moderate", 1, ["moderate"]]) {
    const result = validateInvestmentProfile(value);
    assertEquals(result.ok, false);
    if (!result.ok) {
      assertEquals(result.errors[0]?.message, "must be an object");
    }
  }
});

Deno.test("validateInvestmentProfile rejects non-array excluded_sectors", () => {
  const result = validateInvestmentProfile({
    ...validInvestment,
    excluded_sectors: "tobacco",
  });
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "excluded_sectors");
    assertEquals(result.errors[0]?.message, "must be an array");
  }
});

Deno.test("validateAssetPreferences accepts empty object and watchlists", () => {
  assertEquals(validateAssetPreferences({}).ok, true);
  const withLists = validateAssetPreferences({
    watchlists: { core: ["SPY", "QQQ"] },
    custom_universe: ["NVDA"],
    excluded_tickers: ["GME"],
    excluded_sectors: ["tobacco"],
    schema_version: 1,
  });
  assertEquals(withLists.ok, true);
});

Deno.test("validateAssetPreferences rejects non-array watchlist values", () => {
  const result = validateAssetPreferences({
    watchlists: { core: "SPY" },
  });
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "watchlists.core");
    assertEquals(result.errors[0]?.message, "must be an array");
  }
});

Deno.test("validateAssetPreferences rejects additional top-level properties", () => {
  const result = validateAssetPreferences({ unknown_bucket: [] });
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "unknown_bucket");
    assertEquals(result.errors[0]?.message, "additional property not allowed");
  }
});

Deno.test("validateAgainstSchema reports nested array item type errors", () => {
  const result = validateAgainstSchema(
    {
      type: "object",
      properties: {
        tickers: { type: "array", items: { type: "string" } },
      },
      additionalProperties: false,
    },
    { tickers: ["OK", 1] },
  );
  assertEquals(result.ok, false);
  if (!result.ok) {
    assertEquals(result.errors[0]?.path, "tickers[1]");
    assertEquals(result.errors[0]?.message, "must be a string");
  }
});

Deno.test("HOUSE_PROFILE_KEY stays reserved as house", () => {
  assertEquals(HOUSE_PROFILE_KEY, "house");
});
