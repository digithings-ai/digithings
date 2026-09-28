'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { useAuth } from '@/lib/auth-context';
import { redeemStashedInvite } from '@/lib/invite-auto-redeem';
import {
  hasPendingInvite,
  pathWithoutInviteParam,
  stashInviteFromSearch,
} from '@/lib/invite-stash';
import { requestAccessRefresh } from '@/lib/use-entitlement';

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

/**
 * Module-level redeem flag so AuthGate can hold the shell while a stashed
 * invite is being redeemed (no DigiQuant flash before the fx_hub grant lands).
 */
const REDEEM_TIMEOUT_MS = 10_000;

let redeemInFlight = false;
const redeemListeners = new Set<() => void>();

function setRedeemInFlight(next: boolean): void {
  if (redeemInFlight === next) return;
  redeemInFlight = next;
  for (const listener of [...redeemListeners]) listener();
}

function subscribeRedeem(listener: () => void): () => void {
  redeemListeners.add(listener);
  return () => {
    redeemListeners.delete(listener);
  };
}

function getRedeemInFlight(): boolean {
  return redeemInFlight;
}

function getServerRedeemInFlight(): boolean {
  return false;
}

export type InviteLinkState = { pending: boolean };

/**
 * Stash `?invite=` (sessionStorage) for unsigned visitors, then auto-redeem
 * the existing hashed FX Hub invite once a session with an email exists.
 * Login/signup UI stays code-free; the paste form remains the fallback.
 * `pending` is true while a stashed code is redeeming so callers can defer
 * rendering until the grant (and its access refresh) settles.
 */
export function useInviteLink(): InviteLinkState {
  const { authEnabled, session, loading } = useAuth();
  const pending = useSyncExternalStore(
    subscribeRedeem,
    getRedeemInFlight,
    getServerRedeemInFlight,
  );

  useEffect(() => {
    if (!authEnabled || typeof window === 'undefined') return;
    stashInviteFromSearch(window.location.search);
    const next = pathWithoutInviteParam(currentPath());
    if (next !== currentPath()) {
      window.history.replaceState(window.history.state, '', next);
    }
  }, [authEnabled]);

  const accessToken = session?.access_token;
  const email = session?.user?.email;

  useEffect(() => {
    if (!authEnabled || loading) return;
    if (!accessToken || !email || !hasPendingInvite()) {
      setRedeemInFlight(false);
      return;
    }
    let cancelled = false;
    setRedeemInFlight(true);
    // Bounded wait: a stalled redeem must not pin AuthGate forever.
    const timeout = new Promise<never>((_, reject) => {
      window.setTimeout(
        () => reject(new Error('invite redeem timed out')),
        REDEEM_TIMEOUT_MS,
      );
    });
    void Promise.race([
      redeemStashedInvite({
        accessToken,
        email,
        refresh: requestAccessRefresh,
      }),
      timeout,
    ]).then(() => {
      if (!cancelled) setRedeemInFlight(false);
    });
    return () => {
      cancelled = true;
    };
  }, [authEnabled, loading, accessToken, email]);

  return { pending };
}
