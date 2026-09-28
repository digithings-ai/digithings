'use client';

import type { ReactNode } from 'react';
import { LockedSurface } from '@/components/locked-surface';
import { can, type ArtifactClass, type PlanTier } from '@/lib/entitlements';
import { usePlanTier } from '@/lib/use-entitlement';

export interface EntitledSurfaceProps {
  artifactClass: ArtifactClass;
  children: ReactNode;
  /**
   * Optional tier override for tests and static markup.
   * Production callers omit this — the session (or enterprise default) wins.
   */
  tier?: PlanTier;
  className?: string;
}

/**
 * Panel-level entitlement gate. Renders children when allowed; otherwise a calm
 * LockedSurface. Does not fork whole pages — wrap the panel/section only.
 *
 * Locked panels must render correctly with empty data in either order
 * (locked-then-empty / empty-then-locked): this component ignores children when
 * locked, so empty payloads never surface as errors.
 */
export function EntitledSurface({
  artifactClass,
  children,
  tier: tierOverride,
  className,
}: EntitledSurfaceProps) {
  const sessionTier = usePlanTier();
  const tier = tierOverride ?? sessionTier;
  if (!can(tier, artifactClass)) {
    return (
      <LockedSurface
        tier={tier}
        artifactClass={artifactClass}
        className={className}
      />
    );
  }
  return <>{children}</>;
}
