'use client';

import { useContext, useEffect, useState } from 'react';
import { AuthContext } from './auth-context';
import {
  canAccessProduct,
  resolveClientAccess,
  type AccessSnapshot,
  type ClientProductKey,
} from './access';
import {
  can,
  type ArtifactClass,
  type PlanTier,
} from './entitlements';
import { getSupabaseClient, isOlympusAuthEnabled } from './supabase';

const EMPTY_ACCESS: AccessSnapshot = {
  email: null,
  workspaceId: null,
  workspacePlanTier: 'free',
  planFloor: null,
  effectivePlanTier: 'free',
  products: [],
};

/**
 * Resolve the caller's *effective* plan tier for UI gating.
 * Auth flag off → enterprise (operator parity). Outside AuthProvider with auth
 * on → free (fail closed). When `my_access` / env creator grants elevate the
 * floor, that wins over a free JWT claim (creator without Stripe).
 */
export function usePlanTier(): PlanTier {
  const access = useAccessSnapshot();
  if (!isOlympusAuthEnabled()) return 'enterprise';
  return access.effectivePlanTier;
}

/** Whether the current session may see `artifactClass` in the UI. */
export function useCan(artifactClass: ArtifactClass): boolean {
  return can(usePlanTier(), artifactClass);
}

/** Client product visibility (FX Hub now; future custom Olympus products). */
export function useCanAccessProduct(productKey: ClientProductKey | string): boolean {
  if (!isOlympusAuthEnabled()) return true; // pre-cutover operator parity
  const access = useAccessSnapshot();
  return canAccessProduct(access.products, productKey);
}

/**
 * Load `my_access` RPC when authenticated; fall back to env creator allowlist.
 * Re-resolves when the session user id changes.
 */
export function useAccessSnapshot(): AccessSnapshot {
  const ctx = useContext(AuthContext);
  const authOn = isOlympusAuthEnabled();
  const [rpc, setRpc] = useState<Parameters<typeof resolveClientAccess>[0]['rpc']>(
    null,
  );

  const userId = ctx?.session?.user?.id ?? null;
  const session = ctx?.session ?? null;

  useEffect(() => {
    if (!authOn || !userId) {
      setRpc(null);
      return;
    }
    const client = getSupabaseClient();
    if (!client) {
      setRpc(null);
      return;
    }
    let cancelled = false;
    client
      .rpc('my_access' as never)
      .then(({ data, error }: { data: unknown; error: { message?: string } | null }) => {
        if (cancelled) return;
        if (error || !data || typeof data !== 'object') {
          setRpc(null);
          return;
        }
        setRpc(data as NonNullable<Parameters<typeof resolveClientAccess>[0]['rpc']>);
      })
      .catch(() => {
        if (!cancelled) setRpc(null);
      });
    return () => {
      cancelled = true;
    };
  }, [authOn, userId]);

  if (!authOn) {
    return {
      ...EMPTY_ACCESS,
      effectivePlanTier: 'enterprise',
      workspacePlanTier: 'enterprise',
      products: ['fx_hub'],
    };
  }
  if (!ctx) return EMPTY_ACCESS;
  return resolveClientAccess({ session, rpc });
}
