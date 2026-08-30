'use client';

import { useState } from 'react';
import {
  createCheckoutSession,
  createCustomerPortal,
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

export type BillingTabProps = {
  api: SettingsApiOptions | null;
  configured?: boolean;
  checkoutFn?: typeof createCheckoutSession;
  portalFn?: typeof createCustomerPortal;
  defaultInterval?: BillingInterval;
};

export function BillingTab({
  api,
  configured = isBillingConfigured(),
  checkoutFn = createCheckoutSession,
  portalFn = createCustomerPortal,
  defaultInterval = 'annual',
}: BillingTabProps) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [interval, setInterval] = useState<BillingInterval>(defaultInterval);

  if (!configured) {
    return (
      <div className="space-y-3" data-testid="settings-billing-tab">
        <h2 className="font-display text-xl text-ink tracking-tight">Billing</h2>
        <p className="text-sm text-ink-mute" data-testid="billing-not-configured">
          Billing is not configured. Plan changes and invoices will appear here once Stripe
          checkout and portal are wired for this environment.
        </p>
      </div>
    );
  }

  async function startCheckout(tier: PaidCheckoutTier) {
    if (!api) {
      setMessage('Sign in to manage billing.');
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const session = await checkoutFn(api, { tier, interval });
      if (session.url) {
        window.location.assign(session.url);
      } else {
        setMessage('Checkout session created without a URL.');
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Unable to start checkout.');
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

  return (
    <div
      className="space-y-5"
      data-testid="settings-billing-tab"
      data-interval={interval}
    >
      <div>
        <h2 className="font-display text-xl text-ink tracking-tight">Billing</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Brief unlocks the house digest and portfolio. Desk adds the house pipeline and
          paper brokers. Studio adds your overlay, private book, and BYOK.
        </p>
      </div>

      <div
        className="inline-flex border border-hair"
        role="group"
        aria-label="Billing interval"
      >
        <button
          type="button"
          aria-pressed={interval === 'monthly'}
          disabled={busy}
          onClick={() => setInterval('monthly')}
          className={
            interval === 'monthly'
              ? 'bg-ink px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50'
              : 'px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50'
          }
          data-testid="billing-interval-monthly"
        >
          Monthly
        </button>
        <button
          type="button"
          aria-pressed={interval === 'annual'}
          disabled={busy}
          onClick={() => setInterval('annual')}
          className={
            interval === 'annual'
              ? 'bg-ink px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50'
              : 'px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50'
          }
          data-testid="billing-interval-annual"
        >
          {annualToggleLabel()}
        </button>
      </div>

      <div
        className="border border-hair divide-y divide-hair"
        data-testid="billing-plan-table"
      >
        {PAID_PLAN_CATALOG.map((plan) => {
          const lines = planPriceLines(plan, interval);
          const primary = plan.id === 'studio';
          return (
            <div
              key={plan.id}
              className="grid grid-cols-[minmax(0,1fr)_9.5rem_10.5rem] items-center gap-x-4 px-4 py-3"
              data-testid={`billing-plan-${plan.id}`}
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink">{plan.name}</p>
                <p className="text-sm text-ink-soft">{plan.blurb}</p>
              </div>
              <div className="text-right" data-testid={`billing-price-${plan.id}`}>
                <p className="font-mono text-sm text-ink tabular-nums">
                  <span data-testid="billing-price-hero">{lines.hero}</span>
                </p>
                {lines.listStruck || lines.discount ? (
                  <p className="text-xs text-ink-mute tabular-nums">
                    {lines.listStruck ? (
                      <s data-testid="billing-price-list">{lines.listStruck}</s>
                    ) : null}
                    {lines.discount ? (
                      <>
                        {lines.listStruck ? ' ' : null}
                        <span data-testid="billing-price-discount">{lines.discount}</span>
                      </>
                    ) : null}
                  </p>
                ) : null}
                {lines.caption ? (
                  <p className="text-xs text-ink-mute" data-testid="billing-price-caption">
                    {lines.caption}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void startCheckout(plan.id)}
                className={
                  primary
                    ? 'w-full border border-ink bg-ink px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50'
                    : 'w-full border border-hair px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50'
                }
                data-testid={`billing-checkout-${plan.id}`}
              >
                Upgrade to {plan.name}
              </button>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        disabled={busy}
        onClick={() => void openPortal()}
        className="border border-hair px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50"
        data-testid="billing-portal"
      >
        Customer portal
      </button>

      {message ? (
        <p className="text-sm text-ink-soft" role="status" data-testid="billing-message">
          {message}
        </p>
      ) : null}
    </div>
  );
}
