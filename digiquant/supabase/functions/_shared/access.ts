/**
 * Effective plan tier + client product grants (creator/ops + FX Hub).
 *
 * Source of truth: `entitlement_grants` + `client_product_grants` (migration 108).
 * Effective tier = max(workspaces.plan_tier, plan_floor). UI/EF must use this
 * — never JWT claim alone — so creator access works without Stripe.
 */

import type { PlanTier } from "./tiers.ts";

export type AccessSnapshot = {
  email: string | null;
  workspaceId: string | null;
  workspacePlanTier: PlanTier;
  planFloor: PlanTier | null;
  effectivePlanTier: PlanTier;
  products: readonly string[];
};

const TIER_RANK: Record<PlanTier, number> = {
  free: 0,
  brief: 1,
  desk: 2,
  studio: 3,
  enterprise: 4,
};

export function isPlanTier(value: unknown): value is PlanTier {
  return (
    value === "free" ||
    value === "brief" ||
    value === "desk" ||
    value === "studio" ||
    value === "enterprise"
  );
}

/** Higher of two plan tiers (free < brief < desk < studio < enterprise). */
export function maxPlanTier(a: PlanTier, b: PlanTier | null | undefined): PlanTier {
  if (!b || !isPlanTier(b)) return a;
  return TIER_RANK[a] >= TIER_RANK[b] ? a : b;
}

export function canAccessProduct(
  products: readonly string[] | null | undefined,
  productKey: string,
): boolean {
  if (!products || products.length === 0) return false;
  const key = productKey.trim().toLowerCase();
  return products.some((p) => p.trim().toLowerCase() === key);
}

/** Minimal admin surface used by resolveAccessSnapshot (tests inject fakes). */
export type AccessAdmin = {
  /** PostgREST rpc returns a thenable filter builder — accept any thenable. */
  rpc?: (
    fn: string,
    args?: Record<string, unknown>,
  ) => PromiseLike<{ data: unknown; error: { message?: string } | null }>;
  from: (table: string) => {
    select: (cols: string) => {
      eq: (
        col: string,
        val: string,
      ) => {
        maybeSingle: () => PromiseLike<{
          data: Record<string, unknown> | null;
          error: { message?: string } | null;
        }>;
      };
    };
  };
  /** Optional list helper for product grants (tests). Production uses .from().select().eq(). */
  listProductGrants?: (email: string) => Promise<string[]>;
};

/**
 * Resolve effective access for a user email + authoritative workspace plan_tier.
 * Prefer `my_access` RPC when available; falls back to direct table reads.
 */
export async function resolveAccessSnapshot(args: {
  admin: AccessAdmin;
  email: string | null | undefined;
  workspaceId: string | null | undefined;
  workspacePlanTier: string;
}): Promise<AccessSnapshot> {
  const workspacePlanTier = isPlanTier(args.workspacePlanTier)
    ? args.workspacePlanTier
    : "free";
  const email = (args.email ?? "").trim().toLowerCase() || null;

  if (typeof args.admin.rpc === "function") {
    try {
      const { data, error } = await args.admin.rpc("my_access");
      if (!error && data && typeof data === "object") {
        const row = data as Record<string, unknown>;
        const products = Array.isArray(row.products)
          ? row.products.filter((p): p is string => typeof p === "string")
          : [];
        const floorRaw = row.plan_floor;
        const planFloor =
          isPlanTier(floorRaw) && floorRaw !== "free" ? floorRaw : null;
        const effectiveRaw = row.effective_plan_tier;
        const effectivePlanTier = isPlanTier(effectiveRaw)
          ? effectiveRaw
          : maxPlanTier(workspacePlanTier, planFloor);
        return {
          email: typeof row.email === "string" ? row.email : email,
          workspaceId:
            typeof row.workspace_id === "string"
              ? row.workspace_id
              : args.workspaceId ?? null,
          workspacePlanTier: isPlanTier(row.workspace_plan_tier)
            ? row.workspace_plan_tier
            : workspacePlanTier,
          planFloor,
          effectivePlanTier,
          products,
        };
      }
    } catch {
      // fall through to table reads
    }
  }

  let planFloor: PlanTier | null = null;
  let products: string[] = [];

  if (email) {
    const grantRes = await args.admin
      .from("entitlement_grants")
      .select("plan_floor")
      .eq("email", email)
      .maybeSingle();
    const floorRaw = grantRes.data?.plan_floor;
    if (isPlanTier(floorRaw) && floorRaw !== "free") {
      planFloor = floorRaw;
    }

    if (typeof args.admin.listProductGrants === "function") {
      products = await args.admin.listProductGrants(email);
    } else {
      // PostgREST: select().eq() returns a thenable of rows when not .maybeSingle().
      const prodQuery = args.admin
        .from("client_product_grants")
        .select("product_key")
        .eq("email", email) as unknown as Promise<{
        data: Array<Record<string, unknown>> | null;
        error: { message?: string } | null;
      }>;
      try {
        const prodRes = await prodQuery;
        if (Array.isArray(prodRes.data)) {
          for (const row of prodRes.data) {
            if (typeof row.product_key === "string" && row.product_key.trim()) {
              products.push(row.product_key.trim());
            }
          }
        }
      } catch {
        products = [];
      }
    }

    if (planFloor && !canAccessProduct(products, "fx_hub")) {
      products = [...products, "fx_hub"];
    }
  }

  return {
    email,
    workspaceId: args.workspaceId ?? null,
    workspacePlanTier,
    planFloor,
    effectivePlanTier: maxPlanTier(workspacePlanTier, planFloor),
    products,
  };
}

function requireMinTier(
  effectivePlanTier: PlanTier,
  min: Extract<PlanTier, "desk" | "studio">,
): { ok: true } | { ok: false; message: string } {
  if (TIER_RANK[effectivePlanTier] >= TIER_RANK[min]) {
    return { ok: true };
  }
  return {
    ok: false,
    message:
      min === "desk"
        ? "plan_tier must be desk, studio, or enterprise for this settings action (or hold an ops entitlement grant)"
        : "plan_tier must be studio or enterprise for this settings action (or hold an ops entitlement grant)",
  };
}

/** Desk+ write gate (paper brokers) using *effective* tier. */
export function requireDeskEligible(
  effectivePlanTier: PlanTier,
): { ok: true } | { ok: false; message: string } {
  return requireMinTier(effectivePlanTier, "desk");
}

/** Studio+ write gate (overlay / BYOK) using *effective* tier. */
export function requireStudioEligible(
  effectivePlanTier: PlanTier,
): { ok: true } | { ok: false; message: string } {
  return requireMinTier(effectivePlanTier, "studio");
}
