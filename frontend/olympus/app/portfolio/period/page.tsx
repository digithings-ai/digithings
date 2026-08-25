'use client';

import { useEffect, useState } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { TYPED_CHROME_GAP_COPY } from '@/lib/house-chrome';
import {
  fetchPeriodStatusRows,
  periodStatusLabel,
  type PeriodStatusLoad,
  type PeriodStatusRow,
} from '@/lib/period-status';

function formatPct(value: number | null): string {
  if (value == null || Number.isNaN(value)) return '—';
  const pct = Math.abs(value) <= 1 ? value * 100 : value;
  return `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%`;
}

function formatEquity(value: number): string {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });
}

function PeriodTable({ rows }: { rows: PeriodStatusRow[] }) {
  return (
    <div data-testid="period-status-table" className="overflow-auto border border-hair">
      <table className="w-full table-fixed border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
        <thead className="sticky top-0 z-10 bg-surface">
          <tr className="border-b border-hair text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            <th className="px-3 py-2.5 text-left font-normal">Date</th>
            <th className="px-3 py-2.5 text-left font-normal">Status</th>
            <th className="hidden px-3 py-2.5 text-right font-normal md:table-cell">Open</th>
            <th className="px-3 py-2.5 text-right font-normal">Close</th>
            <th className="px-3 py-2.5 text-right font-normal">Day</th>
            <th className="hidden px-3 py-2.5 text-left font-normal lg:table-cell">Contract</th>
            <th className="hidden px-3 py-2.5 text-left font-normal xl:table-cell">Quality</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hair">
          {rows.map((row) => (
            <tr key={`${row.date}-${row.status}-${row.contract}`}>
              <td className="px-3 py-2.5 text-ink-mute">{row.date}</td>
              <td className="px-3 py-2.5 text-ink">{periodStatusLabel(row.status)}</td>
              <td className="hidden px-3 py-2.5 text-right text-ink-soft md:table-cell">
                {formatEquity(row.opening_equity)}
              </td>
              <td className="px-3 py-2.5 text-right text-ink">{formatEquity(row.closing_equity)}</td>
              <td className="px-3 py-2.5 text-right text-ink-soft">{formatPct(row.day_return_pct)}</td>
              <td className="hidden px-3 py-2.5 text-ink-mute lg:table-cell">{row.contract}</td>
              <td className="hidden px-3 py-2.5 text-ink-mute xl:table-cell">
                {row.quality_reasons?.length ? row.quality_reasons.join(', ') : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Portfolio Period — inspect tip rows from public_accounting_period_status.
 * Incomplete / estimated / failed stay explicit; empty and query failure are typed gaps.
 */
export default function PortfolioPeriodPage() {
  const [load, setLoad] = useState<PeriodStatusLoad | null>(null);

  useEffect(() => {
    let alive = true;
    fetchPeriodStatusRows().then((result) => {
      if (alive) setLoad(result);
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="period" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-4 py-4 md:py-5`}>
        <header className="space-y-1">
          <h2 className="font-display text-2xl font-normal tracking-tight text-ink">
            Accounting periods
          </h2>
          <p className="text-sm text-ink-soft">
            Curated tip status from{' '}
            <code className="font-mono text-xs">public_accounting_period_status</code>. Incomplete
            and failed tips remain visible — never painted as final.
          </p>
        </header>
        {load === null ? (
          <PageSkeleton bare />
        ) : load.kind === 'ok' ? (
          <PeriodTable rows={load.rows} />
        ) : load.kind === 'empty' || load.kind === 'unconfigured' ? (
          <p
            data-testid="typed-chrome-gap"
            className="border border-hair bg-term-bg px-4 py-3 font-mono text-[0.72rem] text-ink-mute"
          >
            {TYPED_CHROME_GAP_COPY.period_empty}
          </p>
        ) : (
          <p
            data-testid="typed-chrome-gap"
            className="border border-hair bg-term-bg px-4 py-3 font-mono text-[0.72rem] text-down"
          >
            {TYPED_CHROME_GAP_COPY.period_query_failed} ({load.message})
          </p>
        )}
      </div>
    </div>
  );
}
