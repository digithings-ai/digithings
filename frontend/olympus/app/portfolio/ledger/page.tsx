'use client';

import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import HouseIdentityBanner from '@/components/house/HouseIdentityBanner';
import HoldingsActivityTable from '@/components/portfolio/HoldingsActivityTable';
import PageSkeleton from '@/components/page-skeleton';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { useDashboard } from '@/lib/dashboard-context';

/**
 * Ledger inspectability — position-event activity already anon-readable.
 * Does not claim access to private portfolio_ledger_* / olympus_accounting_* tables.
 */
export default function PortfolioLedgerPage() {
  const { data, loading, error } = useDashboard();

  if (loading) return <PageSkeleton />;
  if (error || !data) {
    return (
      <div className="flex h-screen items-center justify-center text-down">
        {error || 'Failed to load'}
      </div>
    );
  }

  const events = data.position_events ?? [];

  return (
    <div className="flex min-h-full flex-col">
      <HouseIdentityBanner />
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
