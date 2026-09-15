'use client';

import { useContext, useEffect, useState, useSyncExternalStore } from 'react';
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

/**
 * Shared `my_access` store. One fetch per user + refresh epoch, resolved once
 * and read by every hook instance — otherwise each component resolves its own
 * copy asynchronously and a 12x FX-Hub-only invitee can flash the full
 * DigiQuant chrome (Brief nav, teaser content) before products land.
 */
type AccessStoreSnapshot = {
  userId: string | null;
  rpc: RpcPayload | null;
  pending: boolean;
};

const SERVER_ACCESS_STORE: AccessStoreSnapshot = {
  userId: null,
  rpc: null,
  pending: false,
};

let accessStore: AccessStoreSnapshot = SERVER_ACCESS_STORE;
const accessStoreListeners = new Set<() => void>();

function subscribeAccessStore(listener: () => void): () => void {
  accessStoreListeners.add(listener);
  return () => {
    accessStoreListeners.delete(listener);
  };
}

function getAccessStore(): AccessStoreSnapshot {
  return accessStore;
}

function getServerAccessStore(): AccessStoreSnapshot {
  return SERVER_ACCESS_STORE;
}

function emitAccessStore(next: AccessStoreSnapshot): void {
  accessStore = next;
  for (const listener of [...accessStoreListeners]) listener();
}

let accessEpoch = 0;
let accessLoadKey: string | null = null; // last settled `${userId}:${epoch}`
let accessInFlightKey: string | null = null;

function loadAccess(userId: string): void {
  const key = `${userId}:${accessEpoch}`;
  if (accessLoadKey === key || accessInFlightKey === key) return;
  const client = getSupabaseClient();
  if (!client) {
    accessLoadKey = key;
    emitAccessStore({ userId, rpc: null, pending: false });
    return;
  }
  accessInFlightKey = key;
  emitAccessStore({
    userId,
    rpc: accessStore.userId === userId ? accessStore.rpc : null,
    pending: true,
  });
  void Promise.resolve(client.rpc('my_access' as never)).then(
    (result: RpcResult) => {
      if (accessInFlightKey !== key) return; // superseded by a refresh
      accessInFlightKey = null;
      accessLoadKey = key;
      const { data, error } = result;
      emitAccessStore({
        userId,
        rpc: error || !data || typeof data !== 'object' ? null : (data as RpcPayload),
        pending: false,
      });
    },
    () => {
      if (accessInFlightKey !== key) return;
      accessInFlightKey = null;
      accessLoadKey = key;
      emitAccessStore({ userId, rpc: null, pending: false });
    },
  );
}

const accessRefreshListeners = new Set<() => void>();

/** Re-run `my_access` in every mounted entitlement hook (after invite redeem). */
export function requestAccessRefresh(): void {
  accessEpoch += 1;
  accessLoadKey = null;
  accessInFlightKey = null;
  if (accessStore.userId) loadAccess(accessStore.userId);
  for (const listener of [...accessRefreshListeners]) listener();
}

/**
 * Load `my_access` RPC when authenticated; fall back to env creator allowlist.
 * Re-resolves when the session user id changes or `requestAccessRefresh` fires.
 */
export function useAccessSnapshot(): AccessSnapshot {
  const ctx = useContext(AuthContext);
  const authOn = isDashboardAuthEnabled();
  const [epoch, setEpoch] = useState(0);
  const store = useSyncExternalStore(
    subscribeAccessStore,
    getAccessStore,
    getServerAccessStore,
  );

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
    loadAccess(userId);
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
  return resolveClientAccess({
    session,
    rpc: userId && store.userId === userId ? store.rpc : null,
  });
}

/**
 * True while the signed-in caller's access is still resolving. AuthGate holds
 * the app shell on `AuthLoadingScreen` until this clears so the 12x FX-Hub-only
 * view never flashes the full DigiQuant chrome on first load.
 */
export function useAccessPending(): boolean {
  const ctx = useContext(AuthContext);
  const authOn = isDashboardAuthEnabled();
  const userId = ctx?.session?.user?.id ?? null;
  const store = useSyncExternalStore(
    subscribeAccessStore,
    getAccessStore,
    getServerAccessStore,
  );

  useEffect(() => {
    if (!authOn || !userId) {
      return;
    }
    loadAccess(userId);
  }, [authOn, userId]);

  if (!authOn || !userId) return false;
  return store.userId !== userId || store.pending;
}
