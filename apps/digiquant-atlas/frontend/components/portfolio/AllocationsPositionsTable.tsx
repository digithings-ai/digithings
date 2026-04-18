'use client';

import { Fragment, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { Badge, pnlColor } from '@/components/ui';
import type { DashboardPositionEvent, Position, PositionHistoryRow, Thesis } from '@/lib/types';
import PositionDrilldown from '@/components/portfolio/PositionDrilldown';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';

function thesisNames(ids: string[], thesisById: Map<string, Thesis>): string {
  if (!ids.length) return '—';
  return ids.map((id) => thesisById.get(id)?.name ?? id).join(', ');
}

export default function AllocationsPositionsTable(props: {
  positions: Position[];
  positionHistory: PositionHistoryRow[];
  positionEvents: DashboardPositionEvent[];
  thesisById: Map<string, Thesis>;
  lastUpdated: string | null;
}) {
  const { positions, positionHistory, positionEvents, thesisById, lastUpdated } = props;
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const sorted = useMemo(
    () => [...positions].sort((a, b) => (b.weight_actual ?? 0) - (a.weight_actual ?? 0)),
    [positions]
  );

  const inactive = useMemo<Position[]>(() => {
    if (!showInactive) return [];
    const active = new Set(sorted.map((p) => p.ticker));
    const lastByTicker = new Map<string, PositionHistoryRow>();
    for (const r of positionHistory) {
      const t = String(r.ticker || '').toUpperCase();
      if (!t || active.has(t)) continue;
      const prev = lastByTicker.get(t);
      if (!prev || r.date > prev.date) lastByTicker.set(t, r);
    }
    return [...lastByTicker.values()]
      .map((r) => {
        const t = String(r.ticker).toUpperCase();
        const tid = r.thesis_id ? String(r.thesis_id) : null;
        const p: Position = {
          ticker: t,
          name: 'Former position',
          type: 'LONG',
          weight_actual: 0,
          weight_target: null,
          weight_delta: null,
          current_price: null,
          entry_price: null,
          entry_date: null,
          rationale: '',
          thesis_ids: tid ? [tid] : [],
          category: r.category ?? 'uncategorized',
          pm_notes: '',
          stats: {},
        };
        return p;
      })
      .sort((a, b) => a.ticker.localeCompare(b.ticker));
  }, [positionHistory, showInactive, sorted]);

  const allRows = useMemo(() => [...sorted, ...inactive], [sorted, inactive]);

  const maxWeight = sorted.length ? (sorted[0].weight_actual ?? 0) : 0;

  const colCount = 9;

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="border-b border-border-subtle bg-bg-secondary px-4 py-4 md:px-6 md:py-5 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">Positions</h3>
        <label className="flex items-center gap-2 text-[11px] text-text-muted select-none">
          <input
            type="checkbox"
            className="accent-fin-blue"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          Former positions
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-0 text-sm md:min-w-[920px]">
          <thead>
            <tr className="text-text-muted text-xs uppercase tracking-wider">
              <th className="pl-2 pr-2 py-3 text-left md:pl-4">Ticker</th>
              <th className="hidden max-w-[140px] px-2 py-3 text-left md:table-cell">Name</th>
              <th className="px-2 py-3 text-right md:px-3">Weight</th>
              <th className="hidden px-3 py-3 text-right md:table-cell">Δ weight</th>
              <th className="hidden px-3 py-3 text-left lg:table-cell">Category</th>
              <th className="hidden max-w-[200px] px-3 py-3 text-left xl:table-cell">Thesis</th>
              <th className="hidden px-3 py-3 text-right lg:table-cell">Avg entry</th>
              <th className="px-2 py-3 text-right md:px-3">Last</th>
              <th className="w-8 px-2 py-3 md:px-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {allRows.map((p: Position) => {
              const isExpanded = expandedTicker === p.ticker;
              const w = p.weight_actual ?? 0;
              const pctOfMax = maxWeight > 0 ? (w / maxWeight) * 100 : 0;
              const bar = `linear-gradient(90deg, rgba(59,130,246,0.16) 0%, rgba(59,130,246,0.16) ${pctOfMax}%, rgba(255,255,255,0) ${pctOfMax}%)`;

              return (
                <Fragment key={p.ticker}>
                  <tr
                    onClick={() => setExpandedTicker(isExpanded ? null : p.ticker)}
                    className={`cursor-pointer transition-colors hover:bg-white/[0.03] ${isExpanded ? 'bg-white/[0.02]' : ''}`}
                    style={{ backgroundImage: bar, backgroundRepeat: 'no-repeat' }}
                  >
                        <td className="pl-2 pr-2 py-3 md:pl-4">
                          <Badge variant="blue">{p.ticker}</Badge>
                        </td>
                        <td className="hidden max-w-[140px] truncate px-2 py-3 text-text-secondary md:table-cell">{p.name}</td>
                        <td className="px-2 py-3 text-right font-mono tabular-nums font-medium md:px-3">
                          {p.weight_actual?.toFixed(1)}%
                        </td>
                        <td
                          className={`hidden px-3 py-3 text-right font-mono tabular-nums text-xs md:table-cell ${
                            typeof p.weight_delta === 'number' && p.weight_delta !== 0
                              ? pnlColor(p.weight_delta)
                              : 'text-text-muted'
                          }`}
                        >
                          {typeof p.weight_delta === 'number' && p.weight_delta !== 0
                            ? `${p.weight_delta > 0 ? '+' : ''}${p.weight_delta.toFixed(1)}pp`
                            : '—'}
                        </td>
                        <td className="hidden px-3 py-3 text-xs text-text-secondary lg:table-cell">
                          {formatAllocationCategory(p.category)}
                        </td>
                        <td className="hidden max-w-[200px] px-3 py-3 text-xs text-text-secondary xl:table-cell">
                          {thesisNames(p.thesis_ids, thesisById)}
                        </td>
                        <td className="hidden px-3 py-3 text-right font-mono tabular-nums text-xs text-text-secondary lg:table-cell">
                          {p.entry_price ? `$${p.entry_price.toFixed(2)}` : '—'}
                        </td>
                        <td className="px-2 py-3 text-right font-mono tabular-nums text-xs md:px-3">
                          {p.current_price ? `$${p.current_price.toFixed(2)}` : '—'}
                        </td>
                        <td className="px-2 py-3 text-text-muted md:px-3">{isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-white/[0.02]">
                          <td colSpan={colCount} className="px-4 py-5 md:px-6 md:py-6">
                            <PositionDrilldown
                              key={p.ticker}
                              position={p}
                              positionHistory={positionHistory}
                              positionEvents={positionEvents}
                              thesisById={thesisById}
                              asOfDate={lastUpdated}
                              mode="allocations"
                            />
                          </td>
                        </tr>
                      )}
                </Fragment>
              );
            })}
            {positions.length === 0 && (
              <tr>
                <td colSpan={colCount} className="text-center py-10 text-text-muted">
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
