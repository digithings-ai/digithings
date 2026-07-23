'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import type { BookReconciliation } from '@/lib/book-reconciliation';
import RiskEnvelopeCell from '@/components/portfolio/RiskEnvelopeCell';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';

/*
 * Ruling (#1450 F4 batch D): stays a local table. Sector group rows, the
 * click-to-expand PositionDrilldown, ReactNode cells (conviction meter, risk
 * envelope, signed decision badge) and responsive column hiding are outside
 * the promoted <SortableTable/> leaderboard grammar — see lib/TABLES.md.
 */
export default function AllocationsPositionsTable(props: {
  reconciliation: BookReconciliation;
}) {
  const { reconciliation } = props;
  const searchParams = useSearchParams();
  const selectedTicker = searchParams?.get('ticker')?.toUpperCase() ?? null;
  const rowRefs = useRef<Map<string, HTMLTableRowElement>>(new Map());

  useEffect(() => {
    if (!selectedTicker) return;
    rowRefs.current.get(selectedTicker)?.scrollIntoView({ block: 'center' });
  }, [selectedTicker]);

  const sorted = useMemo(
    () => [...reconciliation.rows].sort((a, b) => b.normalizedWeight - a.normalizedWeight),
    [reconciliation.rows]
  );

  return (
    <div
      data-region="positions-table"
      className="flex h-full min-h-0 flex-col border border-hair bg-surface"
    >
      <div className="flex items-center justify-between gap-3 border-b border-hair bg-term-bg px-4 py-3 md:px-6">
        <h3 className="font-display text-xl font-normal tracking-tight text-ink">Positions</h3>
        <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
          allocation · risk
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full table-fixed border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
          <colgroup>
            <col className="w-[34%] sm:w-[28%]" />
            <col className="hidden w-[18%] sm:table-column" />
            <col className="w-[22%] sm:w-[18%]" />
            <col className="w-[34%] sm:w-[28%]" />
            <col className="w-[10%] sm:w-[8%]" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b border-hair text-[0.58rem] font-normal uppercase tracking-[0.1em] text-ink-mute">
              <th className="py-[0.7rem] pl-2 pr-2 text-left font-normal md:pl-4">Holding</th>
              <th className="hidden px-3 py-[0.7rem] text-left font-normal sm:table-cell">Category</th>
              <th className="px-2 py-[0.7rem] text-right font-normal md:px-3">Weight / target</th>
              <th className="px-2 py-[0.7rem] text-right font-normal md:px-3">Stop ↔ target</th>
              <th className="px-2 py-[0.7rem] text-right font-normal md:px-3">
                <span className="sr-only">Dossier</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hair">
            {sorted.map((p) => {
                  const tickerKey = p.ticker.toUpperCase();
                  const isSelected = selectedTicker === tickerKey;
                  return (
                      <tr key={p.ticker}
                        ref={(el) => {
                          if (el) rowRefs.current.set(tickerKey, el);
                          else rowRefs.current.delete(tickerKey);
                        }}
                        data-selected={isSelected || undefined}
                        className={`transition-colors hover:bg-ink/[0.03] ${
                          isSelected ? 'bg-accent/[0.06] shadow-[inset_2px_0_0_var(--accent)]' : ''
                        }`}
                      >
                        <td className="max-w-[13rem] py-3 pl-2 pr-2 md:pl-4">
                          <span className="block font-mono font-semibold text-ink">
                            {p.ticker}
                          </span>
                          {p.name.trim().toUpperCase() !== p.ticker.trim().toUpperCase() ? (
                            <span
                              className="mt-0.5 block truncate text-[0.68rem] text-ink-mute"
                              title={p.name}
                            >
                              {p.name}
                            </span>
                          ) : null}
                          <span className="mt-0.5 block truncate text-[0.64rem] text-ink-mute sm:hidden">
                            {formatAllocationCategory(p.category)}
                          </span>
                        </td>
                        <td className="hidden px-3 py-3 text-left text-xs text-ink-soft sm:table-cell">
                          {formatAllocationCategory(p.category)}
                        </td>
                        <td className="px-2 py-3 text-right md:px-3">
                          <span className="block font-medium">{p.normalizedWeight.toFixed(1)}%</span>
                          <span className="mt-0.5 block text-[0.64rem] text-ink-mute">
                            {p.weight_target != null ? `${p.weight_target.toFixed(1)}% target` : 'no target'}
                          </span>
                        </td>
                        <td className="px-2 py-3 md:px-3">
                          <RiskEnvelopeCell
                            stopLossPct={p.stop_loss_pct}
                            targetPctGain={p.target_pct_gain}
                            horizonDays={null}
                          />
                        </td>
                        <td className="px-2 py-3 text-right md:px-3">
                          <Link
                            href={`/portfolio/tickers?ticker=${encodeURIComponent(p.ticker.toUpperCase())}`}
                            className="inline-flex h-8 w-8 items-center justify-center text-ink-mute hover:text-accent"
                            title={`Open ${p.ticker} dossier`}
                            aria-label={`Open ${p.ticker} dossier`}
                          >
                            <ArrowUpRight size={15} aria-hidden />
                          </Link>
                        </td>
                      </tr>
                  );
                })}
            {reconciliation.rows.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-10 text-ink-mute">
                  No active positions
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
