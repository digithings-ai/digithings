'use client';

import { EntitledSurface } from '@/components/entitled-surface';
import { can, type PlanTier } from '@/lib/entitlements';
import { usePlanTier } from '@/lib/use-entitlement';

/**
 * Free-tier portfolio glimpse — ticker names only, no weights/NAV/fills.
 * Baseline+ should render the full book instead (caller gates that separately).
 */
export function PortfolioTeaserSurface({
  tickers,
  tier: tierProp,
}: {
  /** Up to a handful of held symbols — never weights. */
  tickers: readonly string[];
  tier?: PlanTier;
}) {
  const hookTier = usePlanTier();
  const tier = tierProp ?? hookTier;

  // Full book available → no teaser chrome (Baseline+).
  if (can(tier, 'house_weights_nav')) {
    return null;
  }
  if (!can(tier, 'portfolio_teaser')) {
    return null;
  }

  const shown = tickers.filter(Boolean).slice(0, 8);
  return (
    <EntitledSurface artifactClass="portfolio_teaser" tier={tier}>
      <div
        data-testid="portfolio-teaser"
        className="border border-hair bg-term-bg/40 px-4 py-3 space-y-2"
      >
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Portfolio glimpse
        </p>
        {shown.length === 0 ? (
          <p className="text-sm text-ink-soft">
            Active book symbols appear here as a teaser. Weights and connections
            unlock on Baseline and Custom.
          </p>
        ) : (
          <p className="text-sm text-ink-soft">
            Active names:{' '}
            <span className="font-mono text-ink">{shown.join(' · ')}</span>
            {tickers.length > shown.length ? ' · …' : ''}
          </p>
        )}
        <p className="text-xs text-ink-mute">
          Free plan is a teaser — no broker connections, automations, or full
          glass-box detail.
        </p>
      </div>
    </EntitledSurface>
  );
}
