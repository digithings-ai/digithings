import { describe, expect, it, vi } from "vitest";
import {
  DATATAPSTREAM_SUGGESTION_POOL,
  getTenantSuggestionPool,
  pickRandomEmbedSuggestions,
} from "./embed-suggestion-pools";

describe("getTenantSuggestionPool", () => {
  it("returns the DataTapStream pool for datatapstream slug", () => {
    expect(getTenantSuggestionPool("datatapstream")).toEqual([
      ...DATATAPSTREAM_SUGGESTION_POOL,
    ]);
  });

  it("returns undefined for unknown slugs", () => {
    expect(getTenantSuggestionPool("embed")).toBeUndefined();
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
