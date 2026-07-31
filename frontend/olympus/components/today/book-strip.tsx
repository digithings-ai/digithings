'use client';

import Link from 'next/link';
import { Wallet } from 'lucide-react';
import type { Position } from '@/lib/types';
import { reconcileBook } from '@/lib/book-reconciliation';
import { ConvictionMeter } from '@/components/shared/conviction-meter';
import { AsOfBadge } from '@/components/shared/as-of-badge';

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

export function BookStrip({ positions, investedPct, asOfDate }: BookStripProps) {
  const { rows, investedPct: invested, cashPct } = reconcileBook(positions, { investedPct });
  const held = rows
    .filter((r) => r.ticker.toUpperCase() !== 'CASH')
    .sort((a, b) => Math.abs(b.day_change_pct ?? 0) - Math.abs(a.day_change_pct ?? 0));

  return (
    <section data-brief-section="book" className="border-b border-hair px-5 py-5 sm:px-7">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Wallet size={14} className="text-ink-mute" />
          <h2 className="text-xs font-bold uppercase tracking-widest text-ink-mute">
            The book today
          </h2>
          {/* The book's OWN date (nav_history), not the digest date — research can
              stay fresh while the book freezes (#1555); the badge carries the
              stale styling so a lagging book is visibly dated, not silently wrong. */}
          <AsOfBadge date={asOfDate} />
        </div>
        <Link
          href="/portfolio"
          className="shrink-0 text-[10px] font-medium text-accent hover:underline"
        >
          All holdings →
        </Link>
      </div>

      {/* Reconciled Invested / Cash header (F3) */}
      <div className="mb-3 flex gap-6 font-mono text-xs tabular-nums">
        <span className="text-ink-soft">
          Invested <span className="text-ink">{invested.toFixed(0)}%</span>
        </span>
        <span className="text-ink-soft">
          Cash <span className="text-ink">{cashPct.toFixed(0)}%</span>
        </span>
      </div>

      {held.length === 0 ? (
        <p className="text-sm text-ink-mute">No positions held yet — the book is all cash.</p>
      ) : (
        <ul className="divide-y divide-hair/60">
          {held.map((r, i) => {
            const dc = r.day_change_pct;
            const dcColor =
              dc == null ? 'text-ink-mute' : dc >= 0 ? 'text-up' : 'text-down';
            return (
              <li key={`${r.ticker}-${i}`} className="flex items-center gap-3 py-2">
                <span className="w-12 shrink-0 font-mono text-xs font-bold text-ink">
                  {r.ticker}
                </span>
                <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-ink-soft">
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
