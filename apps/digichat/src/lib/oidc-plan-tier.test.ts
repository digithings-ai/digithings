import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { planTierFromOidcClaims } from "./oidc-plan-tier";

const authSrc = readFileSync(join(__dirname, "../auth.ts"), "utf8");

describe("planTierFromOidcClaims", () => {
  it("prefers app_metadata.plan_tier and trims it", () => {
    expect(
      planTierFromOidcClaims({
        app_metadata: { plan_tier: " desk " },
        plan_tier: "free",
      }),
    ).toBe("desk");
  });

  it("falls back to a top-level plan_tier claim", () => {
    expect(planTierFromOidcClaims({ plan_tier: "studio" })).toBe("studio");
  });

  it("ignores a blank claim", () => {
    expect(planTierFromOidcClaims({ plan_tier: "  " })).toBeUndefined();
    expect(planTierFromOidcClaims({})).toBeUndefined();
  });
});

describe("oidc profile wiring", () => {
  it("copies the parsed plan tier onto the user the jwt callback reads", () => {
    expect(authSrc).toContain("planTierFromOidcClaims(claims)");
    expect(authSrc).toContain("app_metadata: { plan_tier: tier }");
    expect(authSrc).toMatch(/profile\(profile\)/);
    expect(authSrc).toContain("token.plan_tier = appMeta.plan_tier");
  });
});
