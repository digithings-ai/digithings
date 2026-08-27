'use client';

import type React from 'react';
import { useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import {
  IconButton,
  TabStrip,
  fmtNum,
  fmtPct,
  relativeMetricsFromReturnSeries,
  runTearsheetPrint,
  tabId,
  tabPanelId,
  toneClass,
} from '@digithings/web';
import type { OlympusTearsheet, PerformanceHoldingRow } from './types';
import {
  PortfolioContributionChart,
} from './PortfolioPerformanceCharts';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';

const PERFORMANCE_TABS = [
  { id: 'current', label: 'Open positions' },
  { id: 'historical', label: 'Closed positions' },
];
const TAB_LABEL = 'Performance holdings';

function ReturnValue({ value }: { value: number | null }) {
  if (value == null) return <>—</>;
  return (
    <span className={toneClass(value)}>
      {value > 0 ? '+' : ''}
      {fmtPct(value)}
    </span>
  );
}

function HoldingsPerformanceTable({
  rows,
  emptyMessage,
  returnLabel,
}: {
  rows: PerformanceHoldingRow[];
  emptyMessage: string;
  returnLabel: 'Unrealized' | 'Realized';
}) {
  if (!rows.length) {
    return <p className="px-6 py-12 text-center text-sm text-ink-mute">{emptyMessage}</p>;
  }

  return (
    <div className="max-h-[22rem] overflow-auto print:max-h-none print:overflow-visible">
      <table className="w-full min-w-[680px] border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
        <thead className="sticky top-0 z-10 bg-surface print:static">
          <tr className="border-b border-hair text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            <th className="px-5 py-2.5 text-left font-normal">Holding</th>
            <th className="px-3 py-2.5 text-left font-normal">Category</th>
            <th className="px-3 py-2.5 text-right font-normal">Weight</th>
            <th className="px-3 py-2.5 text-right font-normal">{returnLabel}</th>
            <th className="px-5 py-2.5 text-right font-normal">As of</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hair">
          {rows.map((row) => (
            <tr key={row.ticker} className="hover:bg-ink/[0.02]">
              <td className="px-5 py-2.5 font-semibold text-ink">{row.ticker}</td>
              <td className="px-3 py-2.5 text-ink-soft">
                {formatAllocationCategory(row.category)}
              </td>
              <td className="px-3 py-2.5 text-right text-ink">
                {row.weightPct != null ? `${row.weightPct.toFixed(1)}%` : '—'}
              </td>
              <td className="px-3 py-2.5 text-right">
                <ReturnValue
                  value={
                    returnLabel === 'Unrealized'
                      ? row.unrealizedReturnPct
                      : row.realizedReturnPct
                  }
                />
              </td>
              <td className="px-5 py-2.5 text-right text-ink-mute">
                {row.attributionDate ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metric({
  label,
  value,
  format = 'percent',
  note,
}: {
  label: string;
  value: number | null;
  format?: 'percent' | 'number' | 'ratio';
  note?: string | null;
}) {
  return (
    <div className="flex min-w-0 flex-col justify-center gap-1 border-r border-hair px-4 py-4 last:border-r-0">
      <dt className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">{label}</dt>
      <dd className="m-0 font-mono text-2xl font-medium tabular-nums text-ink">
        {format === 'number' ? (
          value != null ? value.toFixed(2) : '—'
        ) : format === 'ratio' ? (
          value != null ? fmtNum(value, 2) : '—'
        ) : (
          <ReturnValue value={value} />
        )}
      </dd>
      {note ? <p className="m-0 font-mono text-[0.58rem] text-ink-mute">{note}</p> : null}
    </div>
  );
}

function HoldingsPanel({
  rows,
  title,
  emptyMessage,
  id,
  tabIndex,
  returnLabel,
}: {
  rows: PerformanceHoldingRow[];
  title: string;
  emptyMessage: string;
  id: string;
  tabIndex: number;
  returnLabel: 'Unrealized' | 'Realized';
}) {
  return (
    <section
      role="tabpanel"
      id={tabPanelId(TAB_LABEL, id)}
      aria-labelledby={tabId(TAB_LABEL, id)}
      className="border-x border-b border-hair bg-surface"
    >
      <div className="flex items-center justify-between gap-3 border-b border-hair px-5 py-3">
        <h2 className="font-display text-xl font-normal text-ink">{title}</h2>
        <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
          {returnLabel === 'Unrealized' ? 'open book' : 'recorded exits'}
        </span>
      </div>
      <HoldingsPerformanceTable rows={rows} emptyMessage={emptyMessage} returnLabel={returnLabel} />
      <span className="sr-only">
        Panel {tabIndex + 1} of {PERFORMANCE_TABS.length}
      </span>
    </section>
  );
}

/**
 * Compact realized read under the return band: the headline above marks the
 * whole book (unrealized included, per NAV); this strip is the recorded-exits
 * record only, deliberately smaller so the two are never confused.
 */
function RealizedSummary({ rows }: { rows: PerformanceHoldingRow[] }) {
  const realized = rows
    .map((row) => row.realizedReturnPct)
    .filter((v): v is number => v != null && Number.isFinite(v));
  if (realized.length === 0) return null;
  const winners = realized.filter((v) => v > 0).length;
  const avg = realized.reduce((sum, v) => sum + v, 0) / realized.length;
  const best = Math.max(...realized);
  const worst = Math.min(...realized);
  const pct = (v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  return (
    <div
      data-testid="realized-summary"
      className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-x border-b border-hair bg-surface px-5 py-2 font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute"
    >
      <span className="font-semibold">Realized · closed positions</span>
      <span>{realized.length} exit{realized.length === 1 ? '' : 's'}</span>
      <span>win rate {Math.round((winners / realized.length) * 100)}%</span>
      <span>avg {pct(avg)}</span>
      <span>best {pct(best)}</span>
      <span>worst {pct(worst)}</span>
    </div>
  );
}

export function OlympusTearsheetView({ data }: { data: OlympusTearsheet }) {
  const [activeTab, setActiveTab] = useState(0);
  const [printing, setPrinting] = useState(false);
  const [benchmarkTicker, setBenchmarkTicker] = useState(
    data.benchmarkComparisons.find((comparison) => comparison.ticker === 'SPY')?.ticker ??
      data.benchmarkTicker
  );
  const benchmark =
    data.benchmarkComparisons.find((comparison) => comparison.ticker === benchmarkTicker) ?? null;
  const benchmarkReturnPct = benchmark?.returnPct ?? data.benchmarkReturnPct;
  const portfolioReturnPct = data.netReturnPct;
  const relative = useMemo(
    () =>
      relativeMetricsFromReturnSeries(
        portfolioReturnPct,
        benchmarkReturnPct,
        data.navSeries.map((p) => p.returnPct),
        benchmark?.series.map((p) => p.returnPct) ?? []
      ),
    [portfolioReturnPct, benchmarkReturnPct, data.navSeries, benchmark]
  );
  const relativeReturnPct = relative.excessReturnPct ?? data.relativeReturnPct;
  const performancePeriod =
    data.inceptionDate && data.metricsAsOf
      ? `${data.inceptionDate}–${data.metricsAsOf}`
      : null;

  return (
    <div className="ts-print-root space-y-0">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-hair pb-3">
        <h1 className="font-display text-2xl font-normal text-ink">Performance</h1>
        <div className="flex flex-wrap items-center gap-3">
          {data.benchmarkComparisons.length ? (
            <label
              data-testid="global-benchmark-control"
              className="inline-flex items-center gap-2 font-mono text-[0.68rem] text-ink-mute"
            >
              <span className="uppercase tracking-wider">Benchmark</span>
              <select
                aria-label="Comparison benchmark"
                value={benchmark?.ticker ?? ''}
                onChange={(event) => setBenchmarkTicker(event.target.value)}
                className="h-8 border border-hair bg-surface px-2 font-mono text-[0.72rem] text-ink outline-none focus:border-accent"
              >
                {data.benchmarkComparisons.map((comparison) => (
                  <option key={comparison.ticker} value={comparison.ticker}>
                    {comparison.ticker}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <IconButton
            aria-label="Download performance tear sheet as PDF"
            title="Download PDF"
            onClick={() =>
              runTearsheetPrint({ documentTitle: 'Olympus performance', setPrinting })
            }
          >
            <Download size={17} aria-hidden />
          </IconButton>
        </div>
      </header>

      <section
        data-testid="performance-command-band"
        aria-label="Portfolio returns"
        className="grid grid-cols-1 border-x border-b border-hair bg-surface/80 md:grid-cols-[minmax(0,1fr)_auto]"
      >
        <dl className="m-0 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="Portfolio return" value={portfolioReturnPct} note="since inception" />
          <Metric
            label={benchmark ? `${benchmark.ticker} return` : 'Benchmark return'}
            value={benchmarkReturnPct}
          />
          <Metric label="Excess return" value={relativeReturnPct} note="Rp − Rb" />
          <Metric
            label="Relative gain"
            value={relative.relativeGainPct}
            note="same window as excess"
          />
        </dl>
        <div data-region="stamp" className="flex min-w-[11rem] flex-col items-start justify-center gap-1 border-t border-hair px-5 py-4 font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute md:items-end md:border-l md:border-t-0">
          <span>{performancePeriod ? 'period' : data.metricsAsOf ? 'as of' : 'status'}</span>
          <strong className="font-medium text-accent">
            {performancePeriod ?? data.metricsAsOf ?? 'awaiting persisted metrics'}
          </strong>
        </div>
      </section>

      <section
        data-testid="performance-insight-band"
        aria-label="Risk-adjusted insight metrics"
        className="border-x border-b border-hair bg-surface"
      >
        <dl className="m-0 grid grid-cols-1 sm:grid-cols-2">
          <Metric
            label="Alpha"
            value={relative.alphaPct}
            note="Jensen · Rp − β·Rb (β from daily overlap)"
          />
          <Metric
            label="Information ratio"
            value={relative.informationRatio}
            format="ratio"
            note="ann. mean(active) / tracking error"
          />
        </dl>
      </section>

      <RealizedSummary rows={data.historicalHoldings} />

      <PortfolioContributionChart
        points={data.contributionSeries}
        benchmark={benchmark}
      />

      <div className="border-x border-b border-hair bg-surface px-4 pt-2">
        <TabStrip
          tabs={PERFORMANCE_TABS}
          active={activeTab}
          onChange={setActiveTab}
          label={TAB_LABEL}
          variant="underline"
          // Only true outside of printing (CodeRabbit, PR #2290): the
          // printing branch below renders BOTH HoldingsPanels at once (real
          // ids "current" and "historical" both exist), so sharedPanel's
          // single-active-id assumption would be wrong there — fall back to
          // one aria-controls per tab, which is correct while both panels
          // are genuinely mounted.
          sharedPanel={!printing}
        />
      </div>

      {printing ? (
        <div className="space-y-5">
          <HoldingsPanel
            rows={data.currentHoldings}
            title="Open positions"
            emptyMessage="No open position performance is stored yet."
            id="current"
            tabIndex={0}
            returnLabel="Unrealized"
          />
          <HoldingsPanel
            rows={data.historicalHoldings}
            title="Closed positions"
            emptyMessage="No realized exit performance is stored yet."
            id="historical"
            tabIndex={1}
            returnLabel="Realized"
          />
        </div>
      ) : activeTab === 0 ? (
        <HoldingsPanel
          rows={data.currentHoldings}
          title="Open positions"
          emptyMessage="No open position performance is stored yet."
          id="current"
          tabIndex={0}
          returnLabel="Unrealized"
        />
      ) : (
        <HoldingsPanel
          rows={data.historicalHoldings}
          title="Closed positions"
          emptyMessage="No realized exit performance is stored yet."
          id="historical"
          tabIndex={1}
          returnLabel="Realized"
        />
      )}

      <p className="mt-3 text-right font-mono text-[0.62rem] text-ink-mute">
        Holdings as of {data.holdingsAsOf ?? '—'}
        {data.currentNav != null ? ` · paper NAV index ${data.currentNav.toFixed(2)} (not a headline)` : ''}
      </p>
    </div>
  );
}
