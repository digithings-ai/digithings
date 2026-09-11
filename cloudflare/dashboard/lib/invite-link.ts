'use client';

import { useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';
import { redeemStashedInvite } from '@/lib/invite-auto-redeem';
import { pathWithoutInviteParam, stashInviteFromSearch } from '@/lib/invite-stash';
import { requestAccessRefresh } from '@/lib/use-entitlement';

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

/**
 * Stash `?invite=` (sessionStorage) for unsigned visitors, then auto-redeem
 * the existing hashed FX Hub invite once a session with an email exists.
 * Login/signup UI stays code-free; the paste form remains the fallback.
 */
export function useInviteLink(): void {
  const { authEnabled, session, loading } = useAuth();

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
    void redeemStashedInvite({
      accessToken,
      email,
      refresh: requestAccessRefresh,
    });
  }, [authEnabled, loading, accessToken, email]);
}
