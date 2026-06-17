'use client';

import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
import type { SleeveStackMode } from '@/lib/portfolio-aggregates';
import AllocationsPositionsTable from '@/components/portfolio/AllocationsPositionsTable';
import SleeveHistorySection from '@/components/portfolio/SleeveHistorySection';

export default function AllocationsTab(props: {
  lastUpdated: string | null;
  positions: Position[];
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
    lastUpdated,
    positions,
    positionHistory,
    positionEvents,
    thesisById,
    effHistoryDate,
    onSelectHistoryDate,
    onClearHistoryDate,
    showHistoryDateBanner,
    dateParam,
    historyMode,
    setHistoryMode,
    sleeveData,
    sleeveKeys,
    formatSleeveKey,
  } = props;

  return (
    <div className="space-y-10">
      <AllocationsPositionsTable
        positions={positions}
        positionHistory={positionHistory}
        positionEvents={positionEvents}
        thesisById={thesisById}
        lastUpdated={lastUpdated}
      />
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
