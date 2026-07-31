'use client';

import { useMemo, useState } from 'react';
import { SegmentedControl } from '@digithings/web';
import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
import type { TableRow } from '@/lib/database.types';
import type { SleeveStackMode } from '@/lib/portfolio-aggregates';
import { reconcileBook } from '@/lib/book-reconciliation';
import AllocationsPositionsTable from '@/components/portfolio/AllocationsPositionsTable';
import BookReconciliationStrip from '@/components/portfolio/BookReconciliationStrip';
import HoldingsActivityTable from '@/components/portfolio/HoldingsActivityTable';

export default function AllocationsTab(props: {
  lastUpdated: string | null;
  positions: Position[];
  investedPct: number | null;
  decisions: TableRow<'decision_log'>[];
  positionHistory: PositionHistoryRow[];
  positionEvents: DashboardPositionEvent[];
  thesisById: Map<string, Thesis>;
  effHistoryDate: string | null;
  onSelectHistoryDate: (iso: string) => void;
  onClearHistoryDate: () => void;
  showHistoryDateBanner: boolean;
  dateParam: string | null;
  historyMode: SleeveStackMode;
  setHistoryMode: (m: SleeveStackMode) => void;
  sleeveData: Array<Record<string, number | string>>;
  sleeveKeys: string[];
  formatSleeveKey: (k: string) => string;
}) {
  const {
    lastUpdated, positions, investedPct, positionEvents,
  } = props;
  const [view, setView] = useState<'positions' | 'activity'>('positions');

  const reconciliation = useMemo(() => reconcileBook(positions, { investedPct }), [positions, investedPct]);
  const positionCount = reconciliation.rows.length;

  return (
    <div
      data-region="holdings-frame"
      className="flex min-h-[28rem] flex-1 flex-col overflow-hidden"
    >
      <BookReconciliationStrip
        reconciliation={reconciliation}
        asOfDate={lastUpdated}
        positionCount={positionCount}
      />
      <div className="flex items-center justify-between gap-3 border-x border-b border-hair px-4 py-2 md:px-6">
        <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
          book monitor
        </span>
        <SegmentedControl<'positions' | 'activity'>
          options={['positions', 'activity']}
          value={view}
          onChange={setView}
          dress="accent"
          aria-label="Holdings view"
        />
      </div>
      <div data-region="workspace" className="min-h-0 min-w-0 flex-1">
        {view === 'positions' ? (
          <section data-region="ledger" className="h-full min-h-0 min-w-0">
          <AllocationsPositionsTable reconciliation={reconciliation} />
          </section>
        ) : (
          <HoldingsActivityTable events={positionEvents} />
        )}
      </div>
    </div>
  );
}
