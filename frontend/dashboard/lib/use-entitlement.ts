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
import { getSupabaseClient, isDashboardAuthEnabled } from './supabase';

const EMPTY_ACCESS: AccessSnapshot = {
  email: null,
  workspaceId: null,
  workspacePlanTier: 'free',
  planFloor: null,
  effectivePlanTier: 'free',
  products: [],
};

type RpcPayload = NonNullable<Parameters<typeof resolveClientAccess>[0]['rpc']>;
type RpcResult = { data: unknown; error: { message?: string } | null };

/**
 * Resolve the caller's *effective* plan tier for UI gating.
 * Auth flag off → enterprise (operator parity). Outside AuthProvider with auth
 * on → free (fail closed). When `my_access` / env creator grants elevate the
 * floor, that wins over a free JWT claim (creator without Stripe).
 */
export function usePlanTier(): PlanTier {
  const access = useAccessSnapshot();
  if (!isDashboardAuthEnabled()) return 'enterprise';
  return access.effectivePlanTier;
}

/** Whether the current session may see `artifactClass` in the UI. */
export function useCan(artifactClass: ArtifactClass): boolean {
  return can(usePlanTier(), artifactClass);
}

/** Client product visibility (FX Hub now; future custom dashboard products). */
export function useCanAccessProduct(productKey: ClientProductKey | string): boolean {
  const access = useAccessSnapshot();
  if (!isDashboardAuthEnabled()) return true; // pre-cutover operator parity
  return canAccessProduct(access.products, productKey);
}

const accessRefreshListeners = new Set<() => void>();

/** Re-run `my_access` in every mounted entitlement hook (after invite redeem). */
export function requestAccessRefresh(): void {
  for (const listener of [...accessRefreshListeners]) listener();
}

/**
 * Load `my_access` RPC when authenticated; fall back to env creator allowlist.
 * Re-resolves when the session user id changes or `requestAccessRefresh` fires.
 */
export function useAccessSnapshot(): AccessSnapshot {
  const ctx = useContext(AuthContext);
  const authOn = isDashboardAuthEnabled();
  const [rpc, setRpc] = useState<Parameters<typeof resolveClientAccess>[0]['rpc']>(
    null,
  );
  const [epoch, setEpoch] = useState(0);

  const userId = ctx?.session?.user?.id ?? null;
  const session = ctx?.session ?? null;

  useEffect(() => {
    const bump = () => setEpoch((n) => n + 1);
    accessRefreshListeners.add(bump);
    return () => {
      accessRefreshListeners.delete(bump);
    };
  }, []);

  useEffect(() => {
    if (!authOn || !userId) {
      return;
    }
    const client = getSupabaseClient();
    if (!client) {
      return;
    }
    let cancelled = false;
    void Promise.resolve(client.rpc('my_access' as never)).then(
      (result: RpcResult) => {
        if (cancelled) return;
        const { data, error } = result;
        if (error || !data || typeof data !== 'object') {
          setRpc(null);
          return;
        }
        setRpc(data as RpcPayload);
      },
      () => {
        if (!cancelled) setRpc(null);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [authOn, userId, epoch]);

  if (!authOn) {
    return {
      ...EMPTY_ACCESS,
      effectivePlanTier: 'enterprise',
      workspacePlanTier: 'enterprise',
      products: ['fx_hub'],
    };
  }
  if (!ctx) return EMPTY_ACCESS;
  return resolveClientAccess({ session, rpc: userId ? rpc : null });
}
