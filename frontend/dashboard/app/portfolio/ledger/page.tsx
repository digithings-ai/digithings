'use client';

import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import HoldingsActivityTable from '@/components/portfolio/HoldingsActivityTable';
import PageSkeleton from '@/components/page-skeleton';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { EmptyState } from '@digithings/web';
import { LockedSurface } from '@/components/locked-surface';
import { useDashboard } from '@/lib/dashboard-context';
import { can, type PlanTier } from '@/lib/entitlements';
import { usePlanTier } from '@/lib/use-entitlement';

/**
 * Ledger inspectability — position-event activity already anon-readable.
 * Does not claim access to private portfolio_ledger_* / dashboard_accounting_* tables.
 *
 * Tier: `house_weights_nav` (Baseline+). Fail-closed: LockedSurface renders
 * before loading/error chrome so Observer never waits on the book payload.
 */
export default function PortfolioLedgerPage({
  tier: tierOverride,
}: {
  /** Test override; production reads the session. */
  tier?: PlanTier;
} = {}) {
  const sessionTier = usePlanTier();
  const tier = tierOverride ?? sessionTier;

  // Fail-closed first — both orders (locked-then-loading / loading-then-locked).
  // Dashboard fetch stays in LedgerBody so Observer never hits loading chrome.
  if (!can(tier, 'house_weights_nav')) {
    return (
      <div className="flex min-h-full flex-col" data-testid="ledger-locked">
        <PortfolioSectionNav active="ledger" />
        <div className={`${SUBPAGE_MAX} flex-1 space-y-4 py-4 md:py-5`}>
          <div>
            <h1 className="font-display text-xl font-normal tracking-tight text-ink">Ledger</h1>
            <p className="mt-1 max-w-2xl text-sm text-ink-soft">
              Position-event activity for the house book.
            </p>
          </div>
          <LockedSurface tier={tier} artifactClass="house_weights_nav" />
        </div>
      </div>
    );
  }

  return <LedgerBody />;
}

function LedgerBody() {
  const { data, loading, error } = useDashboard();

  if (loading) return <PageSkeleton />;
  if (error || !data) {
    return (
      <div className={`${SUBPAGE_MAX} py-12`}>
        <EmptyState
          variant="error"
          className="mx-auto max-w-md"
          title="Ledger is temporarily unavailable"
          body={error || 'Failed to load'}
          action={
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-5 inline-flex items-center border border-hair px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-ink/[0.06]"
            >
              Retry
            </button>
          }
        />
      </div>
    );
  }

  const events = data.position_events ?? [];

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="ledger" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-4 py-4 md:py-5`}>
        <div>
          <h1 className="font-display text-xl font-normal tracking-tight text-ink">Ledger</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-soft">
            Position-event activity for the house book. Private append-only ledger tables remain
            service_role-only — this surface shows the public event stream only.
          </p>
        </div>
        {events.length === 0 ? (
          <p className="text-sm text-ink-mute">No position events recorded yet.</p>
        ) : (
          <HoldingsActivityTable events={events} />
        )}
      </div>
    </div>
  );
}
