'use client';

import { LogOut } from 'lucide-react';
import { Badge, Button } from '@digithings/ui/ui';
import { useAuth } from '@/lib/auth-context';
import { planSummary } from '@/lib/settings-plan';
import { planRungId } from '@/lib/settings-runs';
import type { PlanTier } from '@/lib/entitlements';
import { PAID_PLAN_CATALOG } from '@/lib/pricing-catalog';

/** Identity row: who is signed in, on which plan, and the sign-out action. */
export function AccountIdentity({ tier }: { tier: PlanTier }) {
  const { user, signOut } = useAuth();
  const email = user?.email ?? null;
  const rung = planRungId(tier);
  const plan = rung ? (PAID_PLAN_CATALOG.find((p) => p.id === rung)?.name ?? rung) : 'Observer';
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 border border-hair bg-surface px-3 py-2.5"
      data-testid="settings-identity"
    >
      <div className="flex min-w-0 items-center gap-2">
        <span
          className="truncate font-mono text-sm text-ink"
          title={email ?? undefined}
          data-testid="settings-identity-email"
        >
          {email ?? 'not signed in'}
        </span>
        <Badge variant="outline" data-testid="settings-identity-plan">
          {plan}
        </Badge>
        <span className="sr-only">{planSummary(tier)}</span>
      </div>
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          void signOut();
        }}
        className="h-auto gap-2 px-3 py-1.5 text-xs text-ink-soft"
        data-testid="settings-sign-out"
      >
        <LogOut size={14} className="shrink-0 text-ink-mute" aria-hidden />
        <span>Sign out</span>
      </Button>
    </div>
  );
}
