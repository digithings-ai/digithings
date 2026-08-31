'use client';

import Link from 'next/link';
import { Lock } from 'lucide-react';
import {
  requiredTierFor,
  type ArtifactClass,
  type PlanTier,
} from '@/lib/entitlements';

const TIER_LABEL: Record<PlanTier, string> = {
  free: 'Observer',
  baseline: 'Baseline',
  custom: 'Custom',
  enterprise: 'Enterprise',
};

const VALUE_PROP: Record<ArtifactClass, string> = {
  research: 'Research and corpus identity are included on every plan.',
  narrative: 'Portfolio deliberation narrative is included on every plan.',
  digest_summary:
    'Digest conclusions are included on the free plan as a teaser. Full glass-box detail unlocks on Baseline.',
  portfolio_teaser:
    'A light portfolio glimpse is included on the free plan. Weights, NAV, and connections unlock on paid tiers.',
  house_weights_nav:
    'House weights, NAV, tearsheet, ledger, and attribution unlock on Baseline.',
  glassbox_economics:
    'Pipeline attempt and spend economics unlock on Baseline.',
  private_book: 'Your private book unlocks on Custom.',
  broker_status: 'Broker connection status unlocks on Custom.',
  overlay_profile: 'Overlay profile controls unlock on Custom.',
};

export interface LockedSurfaceProps {
  /** Caller's current tier (for the calm status line). */
  tier: PlanTier;
  artifactClass: ArtifactClass;
  className?: string;
}

/**
 * Calm locked-state card for tier-gated panels.
 * Tokens: existing `--accent` + muted ink only — no money-tone utilities, no exclamation marks.
 * Upgrade CTA → Settings → Billing (`/settings#billing`).
 */
export function LockedSurface({
  tier,
  artifactClass,
  className,
}: LockedSurfaceProps) {
  const unlock = requiredTierFor(artifactClass);
  const unlockLabel = TIER_LABEL[unlock];
  const currentLabel = TIER_LABEL[tier];

  return (
    <section
      data-testid="locked-surface"
      data-artifact-class={artifactClass}
      data-plan-tier={tier}
      className={` border border-hair bg-term-bg/50 px-4 py-5 ${className ?? ''}`}
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center border border-accent/30 bg-accent/10 text-accent"
          aria-hidden
        >
          <Lock size={14} />
        </span>
        <div className="min-w-0 space-y-2">
          <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
            {currentLabel} · unlocks with {unlockLabel}
          </p>
          <p className="text-sm text-ink-soft">{VALUE_PROP[artifactClass]}</p>
          <Link
            href="/settings#billing"
            className="inline-flex items-center text-sm font-medium text-accent transition-colors hover:underline"
          >
            Upgrade in Settings → Billing
          </Link>
        </div>
      </div>
    </section>
  );
}
