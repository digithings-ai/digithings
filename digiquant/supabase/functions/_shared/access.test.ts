/**
 * Deno unit tests for creator / product access resolution.
 */
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  canAccessProduct,
  maxPlanTier,
  requireDeskEligible,
  requireStudioEligible,
  resolveAccessSnapshot,
  type AccessAdmin,
} from "./access.ts";

Deno.test("maxPlanTier picks the higher tier", () => {
  assertEquals(maxPlanTier("free", "brief"), "brief");
  assertEquals(maxPlanTier("studio", "desk"), "studio");
  assertEquals(maxPlanTier("enterprise", null), "enterprise");
  assertEquals(maxPlanTier("free", undefined), "free");
});

Deno.test("canAccessProduct is case-insensitive", () => {
  assertEquals(canAccessProduct(["fx_hub"], "FX_HUB"), true);
  assertEquals(canAccessProduct(["fx_hub"], "other"), false);
  assertEquals(canAccessProduct([], "fx_hub"), false);
});

Deno.test("requireDeskEligible allows desk+", () => {
  assertEquals(requireDeskEligible("desk").ok, true);
  assertEquals(requireDeskEligible("studio").ok, true);
  assertEquals(requireDeskEligible("enterprise").ok, true);
  assertEquals(requireDeskEligible("brief").ok, false);
  assertEquals(requireDeskEligible("free").ok, false);
});

Deno.test("requireStudioEligible allows studio/enterprise only", () => {
  assertEquals(requireStudioEligible("studio").ok, true);
  assertEquals(requireStudioEligible("enterprise").ok, true);
  assertEquals(requireStudioEligible("desk").ok, false);
  assertEquals(requireStudioEligible("brief").ok, false);
  assertEquals(requireStudioEligible("free").ok, false);
});

Deno.test("resolveAccessSnapshot elevates free workspace via plan_floor", async () => {
  const admin: AccessAdmin = {
    from: (table: string) => ({
      select: (_cols: string) => ({
        eq: (_col: string, _val: string) => ({
          maybeSingle: async () => {
            if (table === "entitlement_grants") {
              return { data: { plan_floor: "studio" }, error: null };
            }
            return { data: null, error: null };
          },
        }),
      }),
    }),
    listProductGrants: async () => ["fx_hub"],
  };

  const snap = await resolveAccessSnapshot({
    admin,
    email: "chris.stefan@proton.me",
    workspaceId: "ws-1",
    workspacePlanTier: "free",
  });
  assertEquals(snap.effectivePlanTier, "studio");
  assertEquals(snap.planFloor, "studio");
  assertEquals(canAccessProduct(snap.products, "fx_hub"), true);
});

Deno.test("resolveAccessSnapshot without email stays free", async () => {
  const admin: AccessAdmin = {
    from: () => ({
      select: () => ({
        eq: () => ({
          maybeSingle: async () => ({ data: null, error: null }),
        }),
      }),
    }),
  };
  const snap = await resolveAccessSnapshot({
    admin,
    email: null,
    workspaceId: null,
    workspacePlanTier: "free",
  });
  assertEquals(snap.effectivePlanTier, "free");
  assertEquals(snap.products.length, 0);
});

Deno.test("resolveAccessSnapshot prefers my_access RPC", async () => {
  const admin: AccessAdmin = {
    rpc: async () => ({
      data: {
        email: "ops@example.com",
        workspace_id: "ws-9",
        workspace_plan_tier: "free",
        plan_floor: "brief",
        effective_plan_tier: "brief",
        products: ["fx_hub"],
      },
      error: null,
    }),
    from: () => {
      throw new Error("should not hit tables when RPC works");
    },
  };
  const snap = await resolveAccessSnapshot({
    admin,
    email: "ops@example.com",
    workspaceId: "ws-9",
    workspacePlanTier: "free",
  });
  assertEquals(snap.effectivePlanTier, "brief");
  assertEquals(canAccessProduct(snap.products, "fx_hub"), true);
});
