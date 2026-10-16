'use client';

/**
 * FX-Hub-only view contract for 12x invitees.
 *
 * An account granted `fx_hub` (hashed invite redeem) with no paid plan tier —
 * the 12x trader invite path — gets a single-view dashboard: FX Hub plus the
 * account settings page, nothing else. Paying tiers (brief+) and the
 * studio-floor creator/admin remain unaffected (#3425 follow-up).
 */

import { useAccessSnapshot, useCanAccessProduct } from '@/lib/use-entitlement';

export const FX_HUB_PRODUCT_KEY = 'fx_hub';

const ALLOWED_PREFIXES = ['/twelve-x', '/settings'] as const;

/** Strip the static-export base path so allowlist checks see app routes. */
function normalizePathname(pathname: string): string {
  let path = (pathname || '/').trim();
  if (!path.startsWith('/')) path = `/${path}`;
  if (path === '/dashboard') return '/';
  if (path.startsWith('/dashboard/')) path = path.slice('/dashboard'.length);
  if (path.length > 1 && path.endsWith('/')) path = path.replace(/\/+$/, '');
  return path || '/';
}

/** True when an fx_hub-only invitee may view this route. */
export function isFxHubOnlyAllowedPath(pathname: string): boolean {
  const path = normalizePathname(pathname);
  return ALLOWED_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

/**
 * Shared 12x gating signals: `canFxHub` (product grant present) and
 * `fxHubOnlyInvitee` (grant present, free tier — single-view contract).
 */
export function useFxHubOnlyInvitee(): {
  canFxHub: boolean;
  fxHubOnlyInvitee: boolean;
} {
  const canFxHub = useCanAccessProduct(FX_HUB_PRODUCT_KEY);
  const { effectivePlanTier } = useAccessSnapshot();
  return {
    canFxHub,
    fxHubOnlyInvitee: canFxHub && effectivePlanTier === 'free',
  };
}
