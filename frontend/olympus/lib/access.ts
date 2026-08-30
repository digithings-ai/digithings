/**
 * Client product + creator/ops access (migration 108).
 *
 * `fx_hub` and future custom Olympus products are moderated via
 * `client_product_grants`. Creator emails get a `plan_floor` in
 * `entitlement_grants` so baseline/Kairos works without Stripe.
 */

import type { PlanTier } from './entitlements';
import { effectivePlanTier, isPlanTier, tierFromSession } from './entitlements';
import type { Session } from '@supabase/supabase-js';

/** Known client product keys — extend as new custom Olympus products ship. */
export type ClientProductKey = 'fx_hub';

export type AccessSnapshot = {
  email: string | null;
  workspaceId: string | null;
  workspacePlanTier: PlanTier;
  planFloor: PlanTier | null;
  effectivePlanTier: PlanTier;
  products: readonly string[];
};

export function canAccessProduct(
  products: readonly string[] | null | undefined,
  productKey: string,
): boolean {
  if (!products || products.length === 0) return false;
  const key = productKey.trim().toLowerCase();
  return products.some((p) => p.trim().toLowerCase() === key);
}

/**
 * Build-time / env fallbacks when `my_access` RPC is unavailable (migration
 * not yet applied). Comma-separated emails; not a secret — allowlist only.
 */
export function creatorEmailsFromEnv(
  raw: string | undefined = process.env.NEXT_PUBLIC_OLYMPUS_CREATOR_EMAILS,
): readonly string[] {
  if (!raw?.trim()) return ['chris.stefan@proton.me'];
  return raw
    .split(',')
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

export function productGrantsFromEnv(
  raw: string | undefined = process.env.NEXT_PUBLIC_OLYMPUS_PRODUCT_GRANTS,
): ReadonlyMap<string, readonly string[]> {
  const map = new Map<string, string[]>();
  // Seed creator → fx_hub always (matches migration 108).
  for (const email of creatorEmailsFromEnv()) {
    map.set(email, ['fx_hub']);
  }
  if (!raw?.trim()) return map;
  // Format: email:product[,product];email:product
  for (const entry of raw.split(';')) {
    const [emailRaw, productsRaw] = entry.split(':');
    const email = emailRaw?.trim().toLowerCase();
    if (!email || !productsRaw) continue;
    const products = productsRaw
      .split(',')
      .map((p) => p.trim().toLowerCase())
      .filter(Boolean);
    const prev = map.get(email) ?? [];
    map.set(email, [...new Set([...prev, ...products])]);
  }
  return map;
}

/** Resolve access from session + optional RPC payload / env fallback. */
export function resolveClientAccess(args: {
  session: Session | null | undefined;
  rpc?: Partial<{
    email: string | null;
    workspace_id: string | null;
    workspace_plan_tier: string;
    plan_floor: string | null;
    effective_plan_tier: string;
    products: string[];
  }> | null;
}): AccessSnapshot {
  const claimTier = tierFromSession(args.session);
  const email =
    (args.rpc?.email ?? args.session?.user?.email ?? null)?.trim().toLowerCase() ||
    null;

  if (args.rpc && typeof args.rpc === 'object') {
    const floorRaw = args.rpc.plan_floor;
    const planFloor =
      isPlanTier(floorRaw) && floorRaw !== 'free' ? floorRaw : null;
    const effectiveRaw = args.rpc.effective_plan_tier;
    const products = Array.isArray(args.rpc.products)
      ? args.rpc.products.filter((p): p is string => typeof p === 'string')
      : [];
    return {
      email,
      workspaceId: args.rpc.workspace_id ?? null,
      workspacePlanTier: isPlanTier(args.rpc.workspace_plan_tier)
        ? args.rpc.workspace_plan_tier
        : claimTier,
      planFloor,
      effectivePlanTier: isPlanTier(effectiveRaw)
        ? effectiveRaw
        : effectivePlanTier(claimTier, planFloor),
      products,
    };
  }

  // Env fallback: creator emails get custom floor + fx_hub.
  const creators = creatorEmailsFromEnv();
  const grants = productGrantsFromEnv();
  const isCreator = email !== null && creators.includes(email);
  const planFloor: PlanTier | null = isCreator ? 'custom' : null;
  const products = email ? [...(grants.get(email) ?? [])] : [];
  if (isCreator && !canAccessProduct(products, 'fx_hub')) {
    products.push('fx_hub');
  }

  return {
    email,
    workspaceId: null,
    workspacePlanTier: claimTier,
    planFloor,
    effectivePlanTier: effectivePlanTier(claimTier, planFloor),
    products,
  };
}
