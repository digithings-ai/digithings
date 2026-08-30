'use client';

import { useContext } from 'react';
import { AuthContext } from './auth-context';
import {
  can,
  tierFromSession,
  type ArtifactClass,
  type PlanTier,
} from './entitlements';
import { isOlympusAuthEnabled } from './supabase';

/**
 * Resolve the caller's plan tier for UI gating.
 * Auth flag off → enterprise (operator parity). Outside AuthProvider with auth
 * on → free (fail closed for presentation; RLS still denies payloads).
 */
export function usePlanTier(): PlanTier {
  const ctx = useContext(AuthContext);
  if (!isOlympusAuthEnabled()) return 'enterprise';
  if (!ctx) return 'free';
  return tierFromSession(ctx.session);
}

/** Whether the current session may see `artifactClass` in the UI. */
export function useCan(artifactClass: ArtifactClass): boolean {
  return can(usePlanTier(), artifactClass);
}
