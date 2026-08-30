'use client';

import { useState } from 'react';
import {
  createCheckoutSession,
  createCustomerPortal,
  isBillingConfigured,
  type SettingsApiOptions,
} from '@/lib/settings-api';

export type BillingTabProps = {
  api: SettingsApiOptions | null;
  configured?: boolean;
  checkoutFn?: typeof createCheckoutSession;
  portalFn?: typeof createCustomerPortal;
};

export function BillingTab({
  api,
  configured = isBillingConfigured(),
  checkoutFn = createCheckoutSession,
  portalFn = createCustomerPortal,
}: BillingTabProps) {
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  async function startCheckout(tier: 'baseline' | 'custom') {
    if (!api) {
      setMessage('Sign in to manage billing.');
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const session = await checkoutFn(api, { tier, interval: 'monthly' });
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
    <div className="space-y-5" data-testid="settings-billing-tab">
      <div>
        <h2 className="font-display text-xl text-ink tracking-tight">Billing</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Upgrade for private books and broker overlays, or open the portal for invoices and
          cancellations.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void startCheckout('baseline')}
          className="rounded-lg border border-accent/40 bg-accent/15 px-3 py-1.5 text-sm font-medium text-accent disabled:opacity-50"
          data-testid="billing-checkout-baseline"
        >
          Upgrade to Baseline
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void startCheckout('custom')}
          className="rounded-lg border border-hair px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50"
          data-testid="billing-checkout-custom"
        >
          Upgrade to Custom
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void openPortal()}
          className="rounded-lg border border-hair px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-ink/[0.04] disabled:opacity-50"
          data-testid="billing-portal"
        >
          Customer portal
        </button>
      </div>

      {message ? (
        <p className="text-sm text-ink-soft" role="status" data-testid="billing-message">
          {message}
        </p>
      ) : null}
    </div>
  );
}
