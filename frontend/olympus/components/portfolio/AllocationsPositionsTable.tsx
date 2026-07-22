'use client';

import { useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { pnlColor } from '@/components/ui';
import type { BookReconciliation } from '@/lib/book-reconciliation';
import type { TableRow } from '@/lib/database.types';
import RiskEnvelopeCell from '@/components/portfolio/RiskEnvelopeCell';
import { ConvictionMeter } from '@/components/shared/conviction-meter';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';

/*
 * Ruling (#1450 F4 batch D): stays a local table. Sector group rows, the
 * click-to-expand PositionDrilldown, ReactNode cells (conviction meter, risk
 * envelope, signed decision badge) and responsive column hiding are outside
 * the promoted <SortableTable/> leaderboard grammar — see lib/TABLES.md.
 */
export default function AllocationsPositionsTable(props: {
  reconciliation: BookReconciliation;
  decisionByTicker: Map<string, TableRow<'decision_log'>>;
}) {
  const { reconciliation, decisionByTicker } = props;
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

  // Show the Target column only when at least one position has a target weight set.
  // (WS1 populates weight_target from the pm-rebalance recommended book; it will be
  //  null for every row in portfolios that haven't run through the PM rebalance node.)
  const hasTargets = useMemo(() => sorted.some((p) => p.weight_target != null), [sorted]);

  const colCount = hasTargets ? 9 : 8;

  return (
    <div data-region="positions-table" className="border border-hair bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-hair bg-term-bg px-4 py-3 md:px-6">
        <h3 className="font-display text-xl font-normal tracking-tight text-ink">Positions</h3>
        <span className="font-mono text-xs uppercase tracking-normal text-ink-mute">
          allocation · performance · risk
        </span>
      </div>
      <div className="overflow-x-auto">
        <table
          className={`w-full table-fixed border-collapse font-mono text-xs [font-variant-numeric:tabular-nums] ${
            hasTargets ? 'min-w-[1080px]' : 'min-w-[980px]'
          }`}
        >
          <colgroup>
            <col className="w-[170px]" />
            <col className="w-[110px]" />
            <col className="w-[90px]" />
            <col className="w-[95px]" />
            <col className="w-[80px]" />
            <col className="w-[100px]" />
            <col className="w-[175px]" />
            {hasTargets && <col className="w-[100px]" />}
            <col className="w-[160px]" />
          </colgroup>
          <thead>
            <tr className="border-b border-hair text-xs font-normal uppercase tracking-normal text-ink-mute">
              <th className="py-[0.7rem] pl-2 pr-2 text-left font-normal md:pl-4">Holding</th>
              <th className="px-3 py-[0.7rem] text-left font-normal">Category</th>
              <th className="px-2 py-[0.7rem] text-right font-normal md:px-3">Allocation</th>
              <th className="px-2 py-[0.7rem] text-center font-normal md:px-3">Conviction</th>
              <th className="px-3 py-[0.7rem] text-right font-normal">Day</th>
              <th className="px-3 py-[0.7rem] text-right font-normal">Unrealized</th>
              <th className="px-3 py-[0.7rem] text-right font-normal">Stop ↔ target</th>
              {hasTargets && (
                <th className="px-3 py-[0.7rem] text-right font-normal">Target weight</th>
              )}
              <th className="px-3 py-[0.7rem] text-right font-normal">Follow</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hair">
            {sorted.map((p) => {
                  const tickerKey = p.ticker.toUpperCase();
                  const isSelected = selectedTicker === tickerKey;
                  const dec = decisionByTicker.get(tickerKey);
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
                              className="mt-0.5 block truncate text-xs text-ink-mute"
                              title={p.name}
                            >
                              {p.name}
                            </span>
                          ) : null}
                        </td>
                        <td className="px-3 py-3 text-left text-xs text-ink-soft">
                          {formatAllocationCategory(p.category)}
                        </td>
                        <td className="px-2 py-3 text-right md:px-3">
                          <span className="font-medium">{p.normalizedWeight.toFixed(1)}%</span>
                        </td>
                        <td className="px-2 py-3 text-center md:px-3">
                          {p.conviction != null ? (
                            <div className="flex justify-center">
                              <ConvictionMeter
                                value={Math.min(3, Math.max(1, p.conviction))}
                                max={3}
                                srLabel={`${p.ticker} conviction`}
                              />
                            </div>
                          ) : (
                            <span className="text-ink-mute">—</span>
                          )}
                        </td>
                        <td
                          className={`px-3 py-3 text-right font-mono tabular-nums text-xs ${pnlColor(
                            p.day_change_pct
                          )}`}
                        >
                          {p.day_change_pct != null
                            ? `${p.day_change_pct >= 0 ? '+' : ''}${p.day_change_pct.toFixed(1)}%`
                            : '—'}
                        </td>
                        <td
                          className={`px-3 py-3 text-right font-mono tabular-nums text-xs ${pnlColor(
                            p.unrealized_pnl_pct
                          )}`}
                        >
                          {p.unrealized_pnl_pct != null
                            ? `${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(1)}%`
                            : '—'}
                        </td>
                        <td className="px-3 py-3">
                          <RiskEnvelopeCell
                            stopLossPct={p.stop_loss_pct}
                            targetPctGain={p.target_pct_gain}
                            horizonDays={p.horizon_days}
                          />
                        </td>
                        {hasTargets && (
                          <td className="px-3 py-3 text-right font-mono tabular-nums text-xs text-ink-soft">
                            {p.weight_target != null ? `${p.weight_target.toFixed(1)}%` : '—'}
                          </td>
                        )}
                        <td className="px-3 py-3 text-right">
                          <div className="flex items-center justify-end gap-3 text-xs">
                            {dec ? (
                              <Link
                                href={buildPipelineHref({
                                  date: dec.run_date,
                                  stage: 'selection',
                                  node: `analyst/${p.ticker.toUpperCase()}`,
                                })}
                                className="inline-flex items-center gap-1 text-accent hover:underline"
                                title={`Open ${p.ticker} decision in Pipeline`}
                              >
                                Decision <ArrowUpRight size={11} aria-hidden />
                              </Link>
                            ) : null}
                            <Link
                              href={`/portfolio/tickers?ticker=${encodeURIComponent(p.ticker.toUpperCase())}`}
                              className="inline-flex items-center gap-1 text-ink-mute hover:text-accent hover:underline"
                              title={`Open ${p.ticker} dossier`}
                            >
                              Dossier <ArrowUpRight size={11} aria-hidden />
                            </Link>
                          </div>
                        </td>
                      </tr>
                  );
                })}
            {reconciliation.rows.length === 0 && (
              <tr>
                <td colSpan={colCount} className="text-center py-10 text-ink-mute">
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
