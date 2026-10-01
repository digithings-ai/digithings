'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  createCheckoutSession,
  createCustomerPortal,
  getProfile,
  isBillingConfigured,
  type SettingsApiOptions,
} from '@/lib/settings-api';
import {
  annualToggleLabel,
  PAID_PLAN_CATALOG,
  planPriceLines,
  type BillingInterval,
  type PaidCheckoutTier,
} from '@/lib/pricing-catalog';
import { isPlanTier, type PlanTier } from '@/lib/entitlements';
import { planRungs, planSummary } from '@/lib/settings-plan';
import {
  Badge,
  Button,
  PlanLadder,
  SegmentedControl,
  type PlanRung,
} from '@digithings/ui/ui';

export type PlanSectionProps = {
  api: SettingsApiOptions | null;
  /** Workspace/JWT tier; the profile tip's `plan_tier` wins once loaded. */
  tier?: PlanTier;
  configured?: boolean;
  checkoutFn?: typeof createCheckoutSession;
  portalFn?: typeof createCustomerPortal;
  profileFn?: typeof getProfile;
  defaultInterval?: BillingInterval;
};

/**
 * Plan position on a ladder (Brief, Desk, Studio) with checkout and portal.
 * No usage meters: there is no usage or spend endpoint, so none is drawn.
 */
export function PlanSection({
  api,
  tier = 'free',
  configured = isBillingConfigured(),
  checkoutFn = createCheckoutSession,
  portalFn = createCustomerPortal,
  profileFn = getProfile,
  defaultInterval = 'annual',
}: PlanSectionProps) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [interval, setInterval] = useState<BillingInterval>(defaultInterval);
  const [serverTier, setServerTier] = useState<PlanTier | null>(null);
  const [subscription, setSubscription] = useState<string | null>(null);
  const [lastError, setLastError] = useState<{ code: string; message: string } | null>(null);

  useEffect(() => {
    if (!api) return;
    let live = true;
    profileFn(api)
      .then((p) => {
        if (!live) return;
        if (isPlanTier(p.plan_tier)) setServerTier(p.plan_tier);
        setSubscription(p.subscription_status ?? null);
      })
      .catch(() => {
        /* tier prop stays authoritative for display */
      });
    return () => {
      live = false;
    };
  }, [api, profileFn]);

  const effectiveTier = serverTier ?? tier;
  const rungs = useMemo(() => planRungs(effectiveTier, interval), [effectiveTier, interval]);
  const current = rungs.find((r) => r.current)?.id ?? null;
  const annualBlocked = lastError?.code === 'PRICE_NOT_CONFIGURED';

  if (!configured) {
    return (
      <div className="space-y-3" data-testid="settings-plan-section">
        <p className="text-sm text-ink-mute" data-testid="billing-not-configured">
          Billing is not configured. Plan changes and invoices will appear here once Stripe
          checkout and portal are wired for this environment.
        </p>
      </div>
    );
  }

  async function startCheckout(target: PaidCheckoutTier) {
    if (!api) {
      setMessage('Sign in to manage billing.');
      return;
    }
    setBusy(true);
    setMessage(null);
    setLastError(null);
    try {
      const session = await checkoutFn(api, { tier: target, interval });
      if (session.url) {
        window.location.assign(session.url);
      } else {
        setMessage('Checkout session created without a URL.');
      }
    } catch (err: any) {
      const code = err?.code ?? err?.status ?? 'UNKNOWN';
      const msg = err?.message ?? 'Unable to start checkout.';
      setLastError({ code, message: msg });
      if (code === 'PRICE_NOT_CONFIGURED') {
        setMessage('Annual pricing is not configured. Falling back to monthly interval.');
        setInterval('monthly');
      } else if (code === 'STRIPE_NOT_CONFIGURED') {
        setMessage('Stripe is not configured. Please contact support.');
      } else if (code === 'NO_STRIPE_CUSTOMER') {
        setMessage('No Stripe customer on workspace. Please complete onboarding.');
      } else {
        setMessage(msg);
      }
    } finally {
      setBusy(false);
    }
  }

  async function openPortal() {
    if (!api) {
      setMessage('Sign in to manage billing.');
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const session = await portalFn(api);
      if (session.url) {
        window.location.assign(session.url);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Unable to open customer portal.');
    } finally {
      setBusy(false);
    }
  }

  const ladder: PlanRung[] = rungs.map((r) => {
    const plan = PAID_PLAN_CATALOG.find((p) => p.id === r.id)!;
    const lines = planPriceLines(plan, interval);
    return {
      id: r.id,
      name: <span data-testid={`billing-plan-${r.id}`}>{r.name}</span>,
      detail: (
        <>
          {r.blurb}
          {r.unlocks ? <span className="block">unlocks: {r.unlocks}</span> : null}
        </>
      ),
      meta: (
        <span className="flex items-center gap-3">
          <span className="text-right" data-testid={`billing-price-${r.id}`}>
            <span className="block text-ink" data-testid="billing-price-hero">
              {lines.hero}
            </span>
            {lines.listStruck || lines.discount ? (
              <span className="block text-ink-mute">
                {lines.listStruck ? <s data-testid="billing-price-list">{lines.listStruck}</s> : null}
                {lines.discount ? (
                  <>
                    {lines.listStruck ? ' ' : null}
                    <span data-testid="billing-price-discount">{lines.discount}</span>
                  </>
                ) : null}
              </span>
            ) : null}
            {lines.caption ? (
              <span className="block text-ink-mute" data-testid="billing-price-caption">
                {lines.caption}
              </span>
            ) : null}
          </span>
          {r.upgrade ? (
            <Button
              type="button"
              variant={r.id === 'studio' ? 'default' : 'outline'}
              disabled={busy}
              onClick={() => void startCheckout(r.id)}
              className="h-auto px-3 py-1.5 text-xs"
              data-testid={`billing-checkout-${r.id}`}
            >
              Upgrade to {r.name}
            </Button>
          ) : null}
        </span>
      ),
    };
  });

  return (
    <div className="space-y-4" data-testid="settings-plan-section" data-interval={interval}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" data-testid="plan-current">
          {current ? (PAID_PLAN_CATALOG.find((p) => p.id === current)?.name ?? current) : 'Observer'}
        </Badge>
        {subscription ? (
          <Badge variant="outline" data-testid="plan-subscription-status">
            {subscription}
          </Badge>
        ) : null}
        <span className="sr-only" data-testid="plan-summary">
          {planSummary(effectiveTier, subscription)}
        </span>
      </div>

      <SegmentedControl
        aria-label="Billing interval"
        data-testid="billing-interval"
        value={interval}
        onChange={(next) => {
          if (!busy && !annualBlocked) setInterval(next);
        }}
        options={[
          { value: 'monthly', label: 'Monthly', disabled: busy || annualBlocked },
          { value: 'annual', label: annualToggleLabel(), disabled: busy || annualBlocked },
        ]}
      />
      {annualBlocked ? (
        <p className="text-sm text-ink-soft" data-testid="billing-annual-error">
          {lastError?.message}
        </p>
      ) : null}

      <PlanLadder rungs={ladder} current={current} aria-label="Plan ladder" />

      <Button
        type="button"
        variant="outline"
        disabled={busy}
        onClick={() => void openPortal()}
        className="h-auto px-3 py-1.5 text-sm text-ink-soft"
        data-testid="billing-portal"
      >
        Manage billing
      </Button>

      {message ? (
        <p className="text-sm text-ink-soft" role="status" data-testid="billing-message">
          {message}
        </p>
      ) : null}
    </div>
  );
}
