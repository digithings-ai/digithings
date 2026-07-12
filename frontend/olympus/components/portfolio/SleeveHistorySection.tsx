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

  const enoughHistory = sleeveData.length >= 2;

  return (
    <section className="space-y-4">
      <div className="glass-card p-6 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionTitle className="mb-0">Sleeves</SectionTitle>
          <div className="flex rounded-lg border border-hair overflow-hidden text-xs">
            <button
              type="button"
              onClick={() => setHistoryMode('ticker')}
              className={`px-3 py-1.5 font-medium ${historyMode === 'ticker' ? 'bg-[var(--accent)]/15 text-[var(--accent)]' : 'text-ink-mute hover:bg-ink/[0.04]'}`}
            >
              Ticker
            </button>
            <button
              type="button"
              onClick={() => setHistoryMode('category')}
              className={`px-3 py-1.5 font-medium border-l border-hair ${historyMode === 'category' ? 'bg-[var(--accent)]/15 text-[var(--accent)]' : 'text-ink-mute hover:bg-ink/[0.04]'}`}
            >
              Category
            </button>
            <button
              type="button"
              onClick={() => setHistoryMode('thesis')}
              className={`px-3 py-1.5 font-medium border-l border-hair ${historyMode === 'thesis' ? 'bg-[var(--accent)]/15 text-[var(--accent)]' : 'text-ink-mute hover:bg-ink/[0.04]'}`}
            >
              Thesis
            </button>
          </div>
        </div>
        {showHistoryDateBanner ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/10 px-3 py-2 text-xs">
            <span className="text-ink-soft">
              <span className="font-mono text-ink">{dateParam}</span>
              <span className="text-ink-mute"> — chart or calendar</span>
            </span>
            <button
              type="button"
              onClick={onClearHistoryDate}
              className="shrink-0 px-2 py-1 rounded border border-hair hover:bg-ink/[0.06] text-ink"
            >
              Clear
            </button>
          </div>
        ) : null}
        {enoughHistory ? (
          <div className="h-[380px]" aria-label="Sleeve weights stacked over time">
            <SleeveStackedChart
              data={sleeveData}
              keys={sleeveKeys}
              formatKey={formatSleeveKey}
              selectedDate={effHistoryDate}
              onChartDateSelect={onSelectHistoryDate}
            />
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-ink-mute">
            Sleeve history builds daily — one snapshot so far. The stacked weight chart appears once a second day is recorded.
          </p>
        )}
      </div>
    </section>
  );
}
