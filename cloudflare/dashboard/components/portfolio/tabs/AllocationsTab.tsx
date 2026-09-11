'use client';

import { useMemo } from 'react';
import type { Position, PositionHistoryRow, Thesis } from '@/lib/types';
import type { TableRow } from '@/lib/database.types';
import type { SleeveStackMode } from '@/lib/portfolio-aggregates';
import type { PlanTier } from '@/lib/entitlements';
import { reconcileBook } from '@/lib/book-reconciliation';
import AllocationsPositionsTable from '@/components/portfolio/AllocationsPositionsTable';
import BookReconciliationStrip from '@/components/portfolio/BookReconciliationStrip';
import { EntitledSurface } from '@/components/entitled-surface';

export default function AllocationsTab(props: {
  lastUpdated: string | null;
  positions: Position[];
  decisions: TableRow<'decision_log'>[];
  positionHistory: PositionHistoryRow[];
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
  /** Authoritative invested % from portfolio_metrics / NAV when known. */
  investedPct?: number | null;
  /** Test override for tier gate; production reads the session. */
  tier?: PlanTier;
}) {
  const { lastUpdated, positions, investedPct, tier } = props;

  const reconciliation = useMemo(
    () => reconcileBook(positions, { investedPct }),
    [positions, investedPct]
  );
  const positionCount = reconciliation.rows.length;

  return (
    <EntitledSurface artifactClass="house_weights_nav" tier={tier}>
      <div
        data-region="holdings-frame"
        className="flex min-h-[28rem] flex-1 flex-col overflow-hidden"
      >
        <BookReconciliationStrip
          reconciliation={reconciliation}
          asOfDate={lastUpdated}
          positionCount={positionCount}
        />
        <div data-region="workspace" className="min-h-0 min-w-0 flex-1">
          <section data-region="ledger" className="h-full min-h-0 min-w-0">
            <AllocationsPositionsTable reconciliation={reconciliation} />
          </section>
        </div>
      </div>
    </EntitledSurface>
  );
}
