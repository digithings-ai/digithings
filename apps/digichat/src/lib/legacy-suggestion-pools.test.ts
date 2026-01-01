import { describe, expect, it } from "vitest";
import { LEGACY_TENANT_SUGGESTION_POOLS } from "./legacy-suggestion-pools";

describe("public legacy suggestion pools stand-in", () => {
  it("carries no tenant pool", () => {
    expect(LEGACY_TENANT_SUGGESTION_POOLS).toEqual({});
  });
});
