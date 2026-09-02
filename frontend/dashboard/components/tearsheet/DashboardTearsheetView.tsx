'use client';

import type React from 'react';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Download } from 'lucide-react';
import {
  IconButton,
  fmtNum,
  fmtPct,
  relativeMetricsFromReturnSeries,
  runTearsheetPrint,
  toneClass,
} from '@digithings/web';
import type { PerformanceTearsheet, PerformanceHoldingRow } from './types';
import {
  PortfolioContributionChart,
} from './PortfolioPerformanceCharts';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';
import { ledgerHref } from '@/lib/portfolio-url-state';

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
}: {
  rows: PerformanceHoldingRow[];
  emptyMessage: string;
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
            <th className="px-3 py-2.5 text-right font-normal">Unrealized</th>
            <th className="px-5 py-2.5 text-right font-normal">As of</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hair">
          {rows.map((row) => (
            <tr
              key={row.eventId ?? `${row.ticker}-${row.attributionDate ?? ''}-${row.disposition ?? 'open'}`}
              className="hover:bg-ink/[0.02]"
            >
              <td className="px-5 py-2.5 font-semibold text-ink">{row.ticker}</td>
              <td className="px-3 py-2.5 text-ink-soft">
                {formatAllocationCategory(row.category)}
              </td>
              <td className="px-3 py-2.5 text-right text-ink">
                {row.weightPct != null ? `${row.weightPct.toFixed(1)}%` : '—'}
              </td>
              <td className="px-3 py-2.5 text-right">
                <ReturnValue value={row.unrealizedReturnPct} />
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

function OpenHoldingsPanel({ rows }: { rows: PerformanceHoldingRow[] }) {
  return (
    <section className="border-x border-b border-hair bg-surface" data-testid="open-positions-panel">
      <div className="flex items-center justify-between gap-3 border-b border-hair px-5 py-3">
        <h2 className="font-display text-xl font-normal text-ink">Open positions</h2>
        <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
          open book · unrealized
        </span>
      </div>
      <HoldingsPerformanceTable
        rows={rows}
        emptyMessage="No open position performance is stored yet."
      />
    </section>
  );
}

/**
 * Compact doorway to Ledger (SSOT for exits/trims). Replaces the former Closed
 * positions tearsheet tab so realized fills are not duplicated.
 */
function LedgerDoorway({ sellCount }: { sellCount: number }) {
  const noun =
    sellCount === 1 ? '1 recorded exit or trim' : `${sellCount} recorded exits & trims`;
  return (
    <div
      data-testid="ledger-doorway"
      className="flex flex-wrap items-center justify-between gap-3 border-x border-b border-hair bg-surface px-5 py-2.5 font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute"
    >
      <span>
        {sellCount > 0 ? noun : 'No recorded exits or trims'}
        {' · '}activity lives on Ledger
      </span>
      <Link
        href={ledgerHref()}
        className="font-medium text-accent hover:underline"
        data-testid="ledger-doorway-link"
      >
        Open ledger
      </Link>
    </div>
  );
}

export function PerformanceTearsheetView({ data }: { data: PerformanceTearsheet }) {
  const [, setPrinting] = useState(false);
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
  const sellCount = data.historicalHoldings.length;

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
              runTearsheetPrint({ documentTitle: 'digiquant performance', setPrinting })
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
        <dl className="m-0 grid grid-cols-1 sm:grid-cols-3">
          <Metric label="Portfolio return" value={portfolioReturnPct} note="since inception" />
          <Metric
            label={benchmark ? `${benchmark.ticker} return` : 'Benchmark return'}
            value={benchmarkReturnPct}
          />
          <Metric
            label="Excess return"
            value={relativeReturnPct}
            note={benchmark ? `Rp − ${benchmark.ticker}` : 'Rp − Rb'}
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
            note="ann. mean(daily excess) / tracking error"
          />
        </dl>
      </section>

      <LedgerDoorway sellCount={sellCount} />

      <PortfolioContributionChart
        points={data.contributionSeries}
        benchmark={benchmark}
      />

      <OpenHoldingsPanel rows={data.currentHoldings} />

      <p className="mt-3 text-right font-mono text-[0.62rem] text-ink-mute">
        Holdings as of {data.holdingsAsOf ?? '—'}
        {data.currentNav != null ? ` · paper NAV index ${data.currentNav.toFixed(2)} (not a headline)` : ''}
      </p>
    </div>
  );
}

/** @deprecated Use PerformanceTearsheetView. One-release alias (ADR-0026 wave 3). */
export const OlympusTearsheetView = PerformanceTearsheetView;
