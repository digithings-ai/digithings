'use client';

import Link from 'next/link';
import { Wallet } from 'lucide-react';
import type { Position } from '@/lib/types';
import { reconcileBook } from '@/lib/book-reconciliation';
import { ConvictionMeter } from '@/components/shared/conviction-meter';

/**
 * "The book today" — a compact holdings strip on the F3 reconciled weight basis
 * (Invested / Cash header, normalized per-row weights summing to 100%). Each held
 * row shows ticker · normalized weight · conviction pips (F6) · day move; rows are
 * sorted by |day move| so the day's biggest mover leads. CASH lives in the header,
 * never as a metric-less row. Links to the full Holdings surface (/portfolio).
 */

export interface BookStripProps {
  positions: Position[];
  investedPct: number | null;
  asOfDate: string | null;
}

export function BookStrip({ positions, investedPct }: BookStripProps) {
  const { rows, investedPct: invested, cashPct } = reconcileBook(positions, { investedPct });
  const held = rows
    .filter((r) => r.ticker.toUpperCase() !== 'CASH')
    .sort((a, b) => Math.abs(b.day_change_pct ?? 0) - Math.abs(a.day_change_pct ?? 0));

  return (
    <section className="glass-card px-5 py-4 sm:px-6">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Wallet size={14} className="text-text-muted" />
          <h2 className="text-xs font-bold uppercase tracking-widest text-text-muted">
            The book today
          </h2>
        </div>
        <Link href="/portfolio" className="text-[10px] font-medium text-accent hover:underline">
          All holdings →
        </Link>
      </div>

      {/* Reconciled Invested / Cash header (F3) */}
      <div className="mb-3 flex gap-6 font-mono text-xs tabular-nums">
        <span className="text-text-secondary">
          Invested <span className="text-text-primary">{invested.toFixed(0)}%</span>
        </span>
        <span className="text-text-secondary">
          Cash <span className="text-text-primary">{cashPct.toFixed(0)}%</span>
        </span>
      </div>

      {held.length === 0 ? (
        <p className="text-sm text-text-muted">No positions held yet — the book is all cash.</p>
      ) : (
        <ul className="divide-y divide-border-subtle/60">
          {held.map((r, i) => {
            const dc = r.day_change_pct;
            const dcColor =
              dc == null ? 'text-text-muted' : dc >= 0 ? 'text-fin-green' : 'text-fin-red';
            return (
              <li key={`${r.ticker}-${i}`} className="flex items-center gap-3 py-2">
                <span className="w-12 shrink-0 font-mono text-xs font-bold text-text-primary">
                  {r.ticker}
                </span>
                <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-text-secondary">
                  {r.normalizedWeight.toFixed(1)}%
                </span>
                <span className="shrink-0">
                  {r.conviction != null ? (
                    <ConvictionMeter value={r.conviction} srLabel={`${r.ticker} conviction`} />
                  ) : null}
                </span>
                <span className={`ml-auto shrink-0 font-mono text-xs tabular-nums ${dcColor}`}>
                  {dc == null ? '—' : `${dc > 0 ? '+' : ''}${dc.toFixed(1)}%`}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
