'use client';

import type { ReactNode } from 'react';
import { EntitledSurface } from '@/components/entitled-surface';
import type { PlanTier } from '@/lib/entitlements';

/**
 * Custom-tier workspace surfaces (T5 gates; T3/T4 fill the unlocked bodies).
 * Wrap at panel level — never fork whole Settings/House pages.
 */

function UnlockedNote({ title, body }: { title: string; body: string }) {
  return (
    <div
      data-testid="tier-unlocked-note"
      className="border border-hair bg-term-bg/40 px-4 py-3 space-y-1"
    >
      <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">{title}</p>
      <p className="text-sm text-ink-soft">{body}</p>
    </div>
  );
}

export function PrivateBookSurface({
  children,
  tier,
}: {
  children?: ReactNode;
  tier?: PlanTier;
}) {
  return (
    <EntitledSurface artifactClass="private_book" tier={tier}>
      {children ?? (
        <UnlockedNote
          title="Private book"
          body="Your workspace book is available on this plan. Holdings and fills stay scoped to your workspace."
        />
      )}
    </EntitledSurface>
  );
}

export function BrokerStatusSurface({
  children,
  tier,
}: {
  children?: ReactNode;
  tier?: PlanTier;
}) {
  return (
    <EntitledSurface artifactClass="broker_status" tier={tier}>
      {children ?? (
        <UnlockedNote
          title="Broker status"
          body="Connection fingerprints and venue status are available on this plan. Secrets never round-trip to the client."
        />
      )}
    </EntitledSurface>
  );
}

export function OverlayProfileSurface({
  children,
  tier,
}: {
  children?: ReactNode;
  tier?: PlanTier;
}) {
  return (
    <EntitledSurface artifactClass="overlay_profile" tier={tier}>
      {children ?? (
        <UnlockedNote
          title="Overlay profile"
          body="Versioned overlay pins are available on this plan. House profile keys stay reserved."
        />
      )}
    </EntitledSurface>
  );
}
