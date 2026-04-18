'use client';

import { Fragment, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
import PositionDrilldown from '@/components/portfolio/PositionDrilldown';

export function PositionPnlTable({
  positions,
  priceChartAnchorDate,
  positionHistory,
  positionEvents,
  navWindowStart,
  thesisById,
}: {
  positions: Position[];
  /** When set, rows expand to show contribution + events through this as-of date. */
  priceChartAnchorDate?: string | null;
  positionHistory: PositionHistoryRow[];
  positionEvents: DashboardPositionEvent[];
  /** First date of the Performance range (e.g. 1M / YTD); NAV contribution aligns to this window. */
  navWindowStart?: string | null;
  thesisById: Map<string, Thesis>;
}) {
  const showCharts = Boolean(priceChartAnchorDate);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  if (!positions.length) return null;

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="border-b border-border-subtle bg-bg-secondary px-4 py-4 md:px-6 md:py-5">
        <h3 className="text-lg font-semibold">Position P&amp;L</h3>
        <p className="text-text-muted text-sm mt-1">
          Unrealized vs entry.
          {showCharts ? ' Expand a row for NAV contribution and activity.' : null}
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-0 text-sm md:min-w-[720px]">
          <thead>
            <tr className="text-text-muted text-xs uppercase tracking-wider">
              <th className="px-4 py-4 text-left md:px-6">Ticker</th>
              <th className="px-4 py-4 text-right md:px-6">Weight</th>
              <th className="hidden px-6 py-4 text-right md:table-cell">Entry</th>
              <th className="hidden px-6 py-4 text-right md:table-cell">Current</th>
              <th className="px-4 py-4 text-right md:px-6">P&amp;L %</th>
              <th className="hidden px-6 py-4 text-right sm:table-cell" title="Attributed share of total portfolio return (percentage points)">
                Contrib. (ppt)
              </th>
              {showCharts ? <th className="w-10 px-3 py-4 md:px-6" aria-label="Expand" /> : null}
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {positions.map((p, i) => {
              const entry = p.entry_price;
              const curr = p.current_price;
              const pnlPct =
                p.unrealized_pnl_pct != null && !Number.isNaN(p.unrealized_pnl_pct)
                  ? p.unrealized_pnl_pct
                  : entry && curr && entry > 0
                    ? ((curr - entry) / entry) * 100
                    : null;
              const contrib =
                p.contribution_pct != null && !Number.isNaN(p.contribution_pct)
                  ? p.contribution_pct
                  : pnlPct != null
                    ? (pnlPct * (p.weight_actual || 0)) / 100
                    : null;
              const isOpen = showCharts && expandedRow === i;
              const skipChart = String(p.ticker).toUpperCase() === 'CASH';

              return (
                <Fragment key={`${p.ticker}-${i}`}>
                  <tr
                    onClick={() => {
                      if (!showCharts || skipChart) return;
                      setExpandedRow(isOpen ? null : i);
                    }}
                    className={
                      showCharts && !skipChart
                        ? `cursor-pointer transition-colors hover:bg-white/[0.02] ${isOpen ? 'bg-white/[0.02]' : ''}`
                        : 'hover:bg-white/[0.02] transition-colors'
                    }
                  >
                    <td className="px-4 py-3 font-semibold md:px-6">{p.ticker}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums md:px-6">
                      {p.weight_actual?.toFixed(1)}%
                    </td>
                    <td className="hidden px-6 py-3 text-right font-mono tabular-nums text-text-secondary md:table-cell">
                      {entry ? `$${entry.toFixed(2)}` : '—'}
                    </td>
                    <td className="hidden px-6 py-3 text-right font-mono tabular-nums md:table-cell">
                      {curr ? `$${curr.toFixed(2)}` : '—'}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-mono tabular-nums font-semibold md:px-6 ${
                        pnlPct != null ? (pnlPct >= 0 ? 'text-fin-green' : 'text-fin-red') : ''
                      }`}
                    >
                      {pnlPct != null ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%` : '—'}
                    </td>
                    <td className="hidden px-6 py-3 text-right font-mono tabular-nums text-text-secondary sm:table-cell">
                      {contrib != null ? `${contrib >= 0 ? '+' : ''}${contrib.toFixed(3)} ppt` : '—'}
                    </td>
                    {showCharts ? (
                      <td className="px-3 py-3 text-text-muted md:px-6">
                        {skipChart ? null : isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </td>
                    ) : null}
                  </tr>
                  {isOpen && priceChartAnchorDate && !skipChart ? (
                    <tr className="bg-white/[0.02]">
                      <td colSpan={7} className="border-t border-border-subtle px-4 py-5 md:px-6">
                        <PositionDrilldown
                          key={`${p.ticker}-${priceChartAnchorDate}`}
                          position={p}
                          positionHistory={positionHistory}
                          positionEvents={positionEvents}
                          thesisById={thesisById}
                          asOfDate={priceChartAnchorDate}
                          performanceRange={
                            navWindowStart && priceChartAnchorDate
                              ? { start: navWindowStart, end: priceChartAnchorDate }
                              : null
                          }
                          mode="performance"
                        />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
