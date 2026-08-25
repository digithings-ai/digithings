'use client';

import { useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { periodInspectabilityState } from '@/lib/house-identity';
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

function GapBox({
  state,
  title,
  children,
}: {
  state: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <div
      role="status"
      className="rounded-lg border border-hair bg-term-bg/50 px-4 py-3 text-sm text-ink-soft"
      data-period-state={state}
      data-testid="period-typed-gap"
    >
      <p className="font-medium text-ink">{title}</p>
      <div className="mt-1 space-y-2">{children}</div>
    </div>
  );
}

/**
 * Period inspectability (#2652).
 *
 * Reads curated `public_accounting_period_status` only. Private
 * `olympus_accounting_*` bases remain service_role-only — never queried here.
 */
export default function PeriodInspectPanel() {
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

  const contractState =
    load === null
      ? periodInspectabilityState()
      : periodInspectabilityState(load.kind === 'ok' ? 'ok' : load.kind);

  return (
    <section data-testid="period-inspect-panel" className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-normal tracking-tight text-ink">Period</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-soft">
          Tip status from{' '}
          <code className="font-mono text-[11px]">public_accounting_period_status</code>. Incomplete
          / estimated / failed tips stay explicit. Raw{' '}
          <code className="font-mono text-[11px]">olympus_accounting_*</code> bases stay
          service_role-only.
        </p>
      </div>

      {load === null ? (
        <p className="text-sm text-ink-mute">Loading period tips…</p>
      ) : load.kind === 'ok' ? (
        <>
          <p className="sr-only" data-period-state={contractState}>
            public period status view
          </p>
          <PeriodTable rows={load.rows} />
        </>
      ) : load.kind === 'empty' || load.kind === 'unconfigured' ? (
        <GapBox state={contractState} title="Empty evidence — no public tip rows">
          <p>
            No tip rows in <code className="font-mono text-[11px]">public_accounting_period_status</code>{' '}
            yet. This is an empty evidence state, not a fabricated final period.
          </p>
        </GapBox>
      ) : (
        <GapBox state={contractState} title="Query failed — public period status">
          <p>
            Could not load <code className="font-mono text-[11px]">public_accounting_period_status</code>.
            Check Supabase connectivity; do not treat this as a successful empty book.
          </p>
          <p className="text-xs text-down">{load.message}</p>
        </GapBox>
      )}

      <ul className="space-y-2 text-sm">
        <li>
          <Link href="/portfolio/performance" className="text-accent hover:underline">
            Open Tearsheet (public metrics) →
          </Link>
        </li>
        <li>
          <Link href="/portfolio/ledger" className="text-accent hover:underline">
            Open Ledger (position events) →
          </Link>
        </li>
      </ul>
    </section>
  );
}
