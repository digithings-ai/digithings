import { describe, expect, it, vi } from "vitest";
import {
  DIGITHINGS_SUGGESTION_POOL,
  getTenantSuggestionPool,
  pickRandomEmbedSuggestions,
} from "./embed-suggestion-pools";
import { LEGACY_TENANT_SUGGESTION_POOLS } from "./legacy-suggestion-pools";

describe("getTenantSuggestionPool", () => {
  it("returns undefined for unknown slugs", () => {
    expect(getTenantSuggestionPool("embed")).toBeUndefined();
  });

  it("returns the curated digithings pool for digithings + digithings-ai slugs", () => {
    expect(getTenantSuggestionPool("digithings")).toEqual([...DIGITHINGS_SUGGESTION_POOL]);
    expect(getTenantSuggestionPool("digithings-ai")).toEqual([...DIGITHINGS_SUGGESTION_POOL]);
  });

  it("falls back to a legacy pool for a slug the house does not own", () => {
    for (const [slug, pool] of Object.entries(LEGACY_TENANT_SUGGESTION_POOLS)) {
      expect(getTenantSuggestionPool(slug)).toEqual([...pool]);
    }
  });
});

describe("pickRandomEmbedSuggestions", () => {
  const pool = ["a", "b", "c", "d", "e", "f"];

  it("returns 3–4 items when the pool is large enough", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    const picked = pickRandomEmbedSuggestions(pool);
    expect(picked).toHaveLength(3);
    expect(new Set(picked).size).toBe(3);
    vi.restoreAllMocks();
  });

  it("returns the full pool when it is smaller than min", () => {
    const picked = pickRandomEmbedSuggestions(["one", "two"]);
    expect(picked).toHaveLength(2);
    expect(new Set(picked)).toEqual(new Set(["one", "two"]));
  });

  it("returns an empty array for an empty pool", () => {
    expect(pickRandomEmbedSuggestions([])).toEqual([]);
  });
});
