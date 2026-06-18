'use client';

import type { Position } from '@/lib/types';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

/**
 * Compact price strip for the currently-held non-CASH positions.
 * Shows ticker, latest close, day change %, and allocation weight.
 * Sourced from `positions` (which already carry current_price and day_change_pct
 * derived from price_history in queries.ts) — no extra fetch required.
 */

function fmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return n >= 100 ? n.toFixed(0) : n.toFixed(2);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return '—';
  const n = Number(v);
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

export default function HeldTickerPricesPanel({ positions }: { positions: Position[] }) {
  // Only non-CASH equity positions with a meaningful weight.
  const held = positions.filter(
    (p) => p.ticker.toUpperCase() !== 'CASH' && (p.weight_actual ?? 0) > 0
  );

  if (held.length === 0) return null;

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-secondary">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
          Held positions — latest prices
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-[10px] uppercase tracking-widest text-text-muted">
              <th className="px-5 py-2.5 text-left">Ticker</th>
              <th className="px-5 py-2.5 text-right">Price</th>
              <th className="px-5 py-2.5 text-right">Day</th>
              <th className="px-5 py-2.5 text-right">Weight</th>
              <th className="hidden sm:table-cell px-5 py-2.5 text-right">Since entry</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {held.map((p) => {
              const dayChange = p.day_change_pct ?? null;
              const dayUp = dayChange != null && dayChange >= 0;
              const DayIcon =
                dayChange == null ? Minus : dayUp ? TrendingUp : TrendingDown;
              const dayColor =
                dayChange == null
                  ? 'text-text-muted'
                  : dayUp
                    ? 'text-fin-green'
                    : 'text-fin-red';
              const sinceEntry = p.since_entry_return_pct ?? null;
              const sinceColor =
                sinceEntry == null
                  ? 'text-text-muted'
                  : sinceEntry >= 0
                    ? 'text-fin-green'
                    : 'text-fin-red';
              return (
                <tr
                  key={p.ticker}
                  className="hover:bg-white/[0.025] transition-colors"
                >
                  <td className="px-5 py-2.5">
                    <span className="font-mono text-xs font-bold text-fin-blue">{p.ticker}</span>
                    {p.name && p.name !== p.ticker && (
                      <span className="ml-2 text-[10px] text-text-muted truncate hidden sm:inline">
                        {p.name}
                      </span>
                    )}
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono text-xs tabular-nums text-text-primary">
                    {p.current_price != null ? `$${fmt(p.current_price)}` : '—'}
                  </td>
                  <td className={`px-5 py-2.5 text-right font-mono text-xs tabular-nums ${dayColor}`}>
                    <span className="flex items-center justify-end gap-1">
                      <DayIcon size={11} />
                      {dayChange != null ? fmtPct(dayChange) : '—'}
                    </span>
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono text-xs tabular-nums text-text-secondary">
                    {(p.weight_actual ?? 0).toFixed(1)}%
                  </td>
                  <td
                    className={`hidden sm:table-cell px-5 py-2.5 text-right font-mono text-xs tabular-nums ${sinceColor}`}
                  >
                    {sinceEntry != null ? fmtPct(sinceEntry) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
