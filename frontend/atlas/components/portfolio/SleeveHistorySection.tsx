'use client';

import { SectionTitle } from '@/components/ui';
import { SleeveStackedChart } from '@/components/portfolio/sleeve-stacked-chart';
import type { SleeveStackMode } from '@/lib/portfolio-aggregates';

export default function SleeveHistorySection(props: {
  historyMode: SleeveStackMode;
  setHistoryMode: (m: SleeveStackMode) => void;
  sleeveData: Array<Record<string, number | string>>;
  sleeveKeys: string[];
  formatSleeveKey: (k: string) => string;
  effHistoryDate: string | null;
  onSelectHistoryDate: (iso: string) => void;
  showHistoryDateBanner: boolean;
  dateParam: string | null;
  onClearHistoryDate: () => void;
}) {
  const {
    historyMode,
    setHistoryMode,
    sleeveData,
    sleeveKeys,
    formatSleeveKey,
    effHistoryDate,
    onSelectHistoryDate,
    showHistoryDateBanner,
    dateParam,
    onClearHistoryDate,
  } = props;

  return (
    <section className="space-y-4">
      <div className="glass-card p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionTitle className="mb-0">Sleeves</SectionTitle>
          <div className="flex rounded-lg border border-border-subtle overflow-hidden text-xs">
            <button
              type="button"
              onClick={() => setHistoryMode('ticker')}
              className={`px-3 py-1.5 font-medium ${historyMode === 'ticker' ? 'bg-fin-blue/20 text-fin-blue' : 'text-text-muted hover:bg-white/[0.04]'}`}
            >
              Ticker
            </button>
            <button
              type="button"
              onClick={() => setHistoryMode('category')}
              className={`px-3 py-1.5 font-medium border-l border-border-subtle ${historyMode === 'category' ? 'bg-fin-blue/20 text-fin-blue' : 'text-text-muted hover:bg-white/[0.04]'}`}
            >
              Category
            </button>
            <button
              type="button"
              onClick={() => setHistoryMode('thesis')}
              className={`px-3 py-1.5 font-medium border-l border-border-subtle ${historyMode === 'thesis' ? 'bg-fin-blue/20 text-fin-blue' : 'text-text-muted hover:bg-white/[0.04]'}`}
            >
              Thesis
            </button>
          </div>
        </div>
        {showHistoryDateBanner ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-fin-blue/30 bg-fin-blue/10 px-3 py-2 text-xs">
            <span className="text-text-secondary">
              <span className="font-mono text-text-primary">{dateParam}</span>
              <span className="text-text-muted"> — chart or calendar</span>
            </span>
            <button
              type="button"
              onClick={onClearHistoryDate}
              className="shrink-0 px-2 py-1 rounded border border-border-subtle hover:bg-white/[0.06] text-text-primary"
            >
              Clear
            </button>
          </div>
        ) : null}
        <div className="h-[380px]" aria-label="Sleeve weights stacked over time">
          <SleeveStackedChart
            data={sleeveData}
            keys={sleeveKeys}
            formatKey={formatSleeveKey}
            selectedDate={effHistoryDate}
            onChartDateSelect={onSelectHistoryDate}
          />
        </div>
      </div>
    </section>
  );
}
