'use client';

import { useMemo } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import HoldingsActivityTable from '@/components/portfolio/HoldingsActivityTable';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { useDashboard } from '@/lib/dashboard-context';
import { TYPED_CHROME_GAP_COPY } from '@/lib/house-chrome';

/**
 * Portfolio Ledger — inspectable position-event activity (opens/adds/trims/exits).
 * Reuses dashboard evidence; does not invent ledger rows.
 */
export default function PortfolioLedgerPage() {
  const { data, loading, error } = useDashboard();
  const events = useMemo(() => data?.position_events ?? [], [data?.position_events]);
  const nonHoldCount = useMemo(
    () => events.filter((e) => e.event !== 'HOLD').length,
    [events]
  );

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="ledger" />
      <div className={`${SUBPAGE_MAX} flex min-h-0 flex-1 flex-col space-y-4 py-4 md:py-5`}>
        <header className="space-y-1">
          <h2 className="font-display text-2xl font-normal tracking-tight text-ink">
            Position ledger
          </h2>
          <p className="text-sm text-ink-soft">
            Change events from the house book (<code className="font-mono text-xs">position_events</code>
            ). HOLD rows are omitted so the inspect surface stays decision-dense.
          </p>
        </header>
        {error ? (
          <p className="text-sm text-down">{error}</p>
        ) : loading || !data ? (
          <PageSkeleton bare />
        ) : nonHoldCount === 0 ? (
          <p
            data-testid="typed-chrome-gap"
            className="border border-hair bg-term-bg px-4 py-3 font-mono text-[0.72rem] text-ink-mute"
          >
            {TYPED_CHROME_GAP_COPY.ledger_empty}
          </p>
        ) : (
          <div className="min-h-[28rem] flex-1">
            <HoldingsActivityTable events={events} />
          </div>
        )}
      </div>
    </div>
  );
}
