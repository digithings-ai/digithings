'use client';

import { useMemo } from 'react';
import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
import type { TableRow } from '@/lib/database.types';
import type { SleeveStackMode } from '@/lib/portfolio-aggregates';
import { reconcileBook } from '@/lib/book-reconciliation';
import { latestDecisionByTicker, proposedNotHeld } from '@/lib/holdings-decisions';
import AllocationsPositionsTable from '@/components/portfolio/AllocationsPositionsTable';
import BookReconciliationStrip from '@/components/portfolio/BookReconciliationStrip';
import ProposedByPipelineShelf from '@/components/portfolio/ProposedByPipelineShelf';
import SleeveHistorySection from '@/components/portfolio/SleeveHistorySection';

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
    lastUpdated, positions, investedPct, decisions, positionHistory, positionEvents,
    thesisById, effHistoryDate, onSelectHistoryDate, onClearHistoryDate,
    showHistoryDateBanner, dateParam, historyMode, setHistoryMode,
    sleeveData, sleeveKeys, formatSleeveKey,
  } = props;

  const reconciliation = useMemo(() => reconcileBook(positions, { investedPct }), [positions, investedPct]);
  const decisionByTicker = useMemo(() => latestDecisionByTicker(decisions), [decisions]);
  const heldTickers = useMemo(
    () => new Set(reconciliation.rows.map((p) => p.ticker.toUpperCase())),
    [reconciliation.rows]
  );
  const proposed = useMemo(() => proposedNotHeld(decisions, heldTickers), [decisions, heldTickers]);

  return (
    <div className="space-y-10">
      <BookReconciliationStrip reconciliation={reconciliation} asOfDate={lastUpdated} />
      <AllocationsPositionsTable
        reconciliation={reconciliation}
        positionHistory={positionHistory}
        positionEvents={positionEvents}
        thesisById={thesisById}
        lastUpdated={lastUpdated}
        decisionByTicker={decisionByTicker}
      />
      <ProposedByPipelineShelf proposed={proposed} />
      <SleeveHistorySection
        historyMode={historyMode}
        setHistoryMode={setHistoryMode}
        sleeveData={sleeveData}
        sleeveKeys={sleeveKeys}
        formatSleeveKey={formatSleeveKey}
        effHistoryDate={effHistoryDate}
        onSelectHistoryDate={onSelectHistoryDate}
        showHistoryDateBanner={showHistoryDateBanner}
        dateParam={dateParam}
        onClearHistoryDate={onClearHistoryDate}
      />
    </div>
  );
}
