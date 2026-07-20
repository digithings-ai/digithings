'use client';

import { SectionTitle } from '@/components/ui';
import { SleeveStackedChart } from '@/components/portfolio/sleeve-stacked-chart';
import { SegmentedControl } from '@digithings/web';
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
          <SegmentedControl<SleeveStackMode>
            options={['ticker', 'category', 'thesis']}
            value={historyMode}
            onChange={setHistoryMode}
            dress="accent"
            aria-label="Sleeve grouping mode"
          />
        </div>
        {showHistoryDateBanner ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 text-xs">
            <span className="text-ink-soft">
              <span className="text-ink-mute">Sleeve mix pinned to </span>
              <span className="font-mono text-ink">{dateParam}</span>
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
