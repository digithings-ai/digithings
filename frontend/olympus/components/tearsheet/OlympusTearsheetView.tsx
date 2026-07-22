'use client';

import type React from 'react';
import { useState } from 'react';
import { Download } from 'lucide-react';
import {
  IconButton,
  TabStrip,
  fmtPct,
  runTearsheetPrint,
  tabId,
  tabPanelId,
  toneClass,
} from '@digithings/web';
import type { OlympusTearsheet, PerformanceHoldingRow } from './types';
import {
  PortfolioContributionChart,
} from './PortfolioPerformanceCharts';

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
              <td className="px-3 py-2.5 text-ink-soft">{row.category ?? '—'}</td>
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
}: {
  label: string;
  value: number | null;
  format?: 'percent' | 'number';
}) {
  return (
    <div className="flex min-w-0 flex-col justify-center gap-2 border-r border-hair px-4 py-4 last:border-r-0">
      <dt className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">{label}</dt>
      <dd className="m-0 font-mono text-2xl font-medium tabular-nums text-ink">
        {format === 'number' ? (value != null ? value.toFixed(2) : '—') : <ReturnValue value={value} />}
      </dd>
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

export function OlympusTearsheetView({ data }: { data: OlympusTearsheet }) {
  const [activeTab, setActiveTab] = useState(0);
  const [printing, setPrinting] = useState(false);
  const hasReturns =
    data.netReturnPct != null ||
    data.benchmarkReturnPct != null ||
    data.relativeReturnPct != null;
  const sourceLabel = {
    persisted: 'persisted metrics',
    derived: 'live history fallback',
    mixed: 'persisted + live fallback',
    unavailable: 'returns unavailable',
  }[data.returnsSource];

  return (
    <div className="ts-print-root space-y-0">
      <header className="flex items-center justify-between gap-4 border-b border-hair pb-3">
        <div>
          <p className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
            portfolio performance
          </p>
          <h1 className="mt-1 font-display text-2xl font-normal text-ink">Performance</h1>
        </div>
        <IconButton
          aria-label="Download performance tear sheet as PDF"
          title="Download PDF"
          onClick={() =>
            runTearsheetPrint({ documentTitle: 'Olympus performance', setPrinting })
          }
        >
          <Download size={17} aria-hidden />
        </IconButton>
      </header>

      <section
        data-testid="performance-command-band"
        aria-label="Portfolio returns"
        className="grid grid-cols-1 border-x border-b border-hair bg-surface/80 md:grid-cols-[minmax(0,1fr)_auto]"
      >
        <dl className="m-0 grid grid-cols-1 sm:grid-cols-3">
          <Metric label="NAV" value={data.currentNav} format="number" />
          <Metric label="Portfolio return" value={data.netReturnPct} />
          <Metric label="Active return" value={data.relativeReturnPct} />
        </dl>
        <div className="flex min-w-[11rem] flex-col items-start justify-center gap-1 border-t border-hair px-5 py-4 font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute md:items-end md:border-l md:border-t-0">
          <span>{hasReturns ? 'as of' : 'status'}</span>
          <strong className="font-medium text-accent">
            {data.metricsAsOf ?? 'awaiting persisted metrics'}
          </strong>
          <span>{sourceLabel}</span>
          {data.inceptionDate ? <span>since {data.inceptionDate}</span> : null}
          {data.benchmarkReturnPct != null ? (
            <span>vs {data.benchmarkTicker} {data.benchmarkReturnPct >= 0 ? '+' : ''}{data.benchmarkReturnPct.toFixed(2)}%</span>
          ) : null}
        </div>
      </section>

      <PortfolioContributionChart points={data.contributionSeries} />

      <div className="border-x border-b border-hair bg-surface px-4 pt-2">
        <TabStrip
          tabs={PERFORMANCE_TABS}
          active={activeTab}
          onChange={setActiveTab}
          label={TAB_LABEL}
          variant="underline"
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
      </p>
    </div>
  );
}
