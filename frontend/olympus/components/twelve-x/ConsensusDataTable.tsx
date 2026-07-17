'use client';

import { useMemo, useState } from 'react';
import {
  LEAN_BAND,
  STRONG_BAND,
  currencyColor,
  scoreColorClass,
  scoreLabel,
} from '@/lib/twelve-x/consensus-bar';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { deriveConsensusRows, type ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import { ConsensusScoreBar } from './ConsensusScoreBars';
import DeltaChip from './DeltaChip';

export type RowFilter = 'all' | 'bullish' | 'bearish' | 'strong';
export type SortDir = 'asc' | 'desc';
export type SortKey = 'currency' | 'actualNow' | 'avgNow' | 'priorChange' | 'n_views' | 'agreement';

const FILTERS: { key: RowFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'bullish', label: 'Bullish' },
  { key: 'bearish', label: 'Bearish' },
  { key: 'strong', label: 'Strong' },
];

export function passesFilter(row: ConsensusCurrencyRow, filter: RowFilter): boolean {
  const score = row.actualNow ?? 0;
  if (filter === 'bullish') return score >= LEAN_BAND;
  if (filter === 'bearish') return score <= -LEAN_BAND;
  if (filter === 'strong') return Math.abs(score) >= STRONG_BAND;
  return true;
}

function fmtSigned(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

export interface ConsensusDataTableProps {
  series: FxConsensusSnapshotRow[];
  latest: FxConsensusSnapshotRow[];
  deltas: ConsensusDeltaSet;
  onRowClick?: (ccy: string) => void;
  initialFilter?: RowFilter;
}

export function ConsensusDataTable({
  series,
  latest,
  deltas,
  onRowClick,
  initialFilter = 'all',
}: ConsensusDataTableProps) {
  const [filter, setFilter] = useState<RowFilter>(initialFilter);
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const consensusRows = useMemo<ConsensusCurrencyRow[]>(
    () => deriveConsensusRows(series),
    [series],
  );

  const latestByRow = useMemo(() => {
    const map = new Map<string, FxConsensusSnapshotRow>();
    for (const r of latest) map.set(r.currency, r);
    return map;
  }, [latest]);

  const rows = useMemo<ConsensusCurrencyRow[]>(() => {
    const filtered = consensusRows.filter((row) => passesFilter(row, filter));
    if (sortKey === null) return filtered;

    const mul = sortDir === 'asc' ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortKey === 'currency') {
        return mul * a.currency.localeCompare(b.currency);
      }
      const av = (sortKey === 'n_views' || sortKey === 'agreement')
        ? (latestByRow.get(a.currency)?.[sortKey] ?? null)
        : a[sortKey];
      const bv = (sortKey === 'n_views' || sortKey === 'agreement')
        ? (latestByRow.get(b.currency)?.[sortKey] ?? null)
        : b[sortKey];

      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      return mul * ((av as number) - (bv as number));
    });
  }, [consensusRows, filter, sortKey, sortDir, latestByRow]);

  function onHeaderClick(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'currency' ? 'asc' : 'desc');
    }
  }

  if (rows.length === 0) {
    return (
      <div className="glass-card p-8 text-center text-ink-mute text-sm">
        No consensus data available.
      </div>
    );
  }

  return (
    <div className="space-y-3.5">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter rows">
        {FILTERS.map((f) => {
          const on = filter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              data-filter={f.key}
              aria-pressed={on}
              onClick={() => setFilter(f.key)}
              className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors ${
                on
                  ? 'border-accent/40 bg-accent/15 text-accent'
                  : 'border-hair text-ink-mute hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      <div className="glass-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] border-collapse">
            <thead>
              <tr className="border-b border-hair">
                <th className="px-3.5 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  <button
                    type="button"
                    onClick={() => onHeaderClick('currency')}
                    className="hover:text-ink transition-colors"
                  >
                    Currency
                  </button>
                </th>
                <th className="px-3.5 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  <button
                    type="button"
                    onClick={() => onHeaderClick('actualNow')}
                    className="hover:text-ink transition-colors"
                  >
                    Current
                  </button>
                </th>
                <th className="px-3.5 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  <button
                    type="button"
                    onClick={() => onHeaderClick('avgNow')}
                    className="hover:text-ink transition-colors"
                    title="Trailing 5-run average"
                  >
                    Average
                  </button>
                </th>
                <th className="px-3.5 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  <button
                    type="button"
                    onClick={() => onHeaderClick('priorChange')}
                    className="hover:text-ink transition-colors"
                  >
                    Prior Δ
                  </button>
                </th>
                <th className="px-3.5 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  <button
                    type="button"
                    onClick={() => onHeaderClick('n_views')}
                    className="hover:text-ink transition-colors"
                  >
                    Opinions
                  </button>
                </th>
                <th className="px-3.5 py-2.5 text-right text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  <button
                    type="button"
                    onClick={() => onHeaderClick('agreement')}
                    className="hover:text-ink transition-colors"
                  >
                    Agreement
                  </button>
                </th>
                <th className="px-3.5 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  Score
                </th>
                <th className="px-3.5 py-2.5 text-center text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                  Details
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hair">
              {rows.map((row) => {
                const latestRow = latestByRow.get(row.currency);
                const score = row.actualNow ?? 0;
                const colorClass = scoreColorClass(score);
                const n_views = latestRow?.n_views ?? 0;
                const agreement = latestRow?.agreement ?? 0;
                return (
                  <tr
                    key={row.currency}
                    data-ccy={row.currency}
                    onClick={() => onRowClick?.(row.currency)}
                    className="text-sm hover:bg-ink/[0.02] transition-colors cursor-pointer"
                  >
                    <td className="px-3.5 py-2.5">
                      <span
                        className="font-mono font-semibold text-[13px]"
                        style={{ color: currencyColor(row.currency) }}
                      >
                        {row.currency}
                      </span>
                    </td>
                    <td className={`px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] ${colorClass}`}>
                      {fmtSigned(row.actualNow)}
                    </td>
                    <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] text-ink-soft">
                      {fmtSigned(row.avgNow)}
                    </td>
                    <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] text-ink-soft">
                      {fmtSigned(row.priorChange)}
                    </td>
                    <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] text-ink-soft">
                      {n_views}
                    </td>
                    <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] text-ink-soft">
                      {agreement !== null && Number.isFinite(agreement) ? `${Math.round(agreement * 100)}%` : '—'}
                    </td>
                    <td className="px-3.5 py-2.5">
                      <div className="flex min-w-[120px]">
                        <ConsensusScoreBar value={score} />
                      </div>
                    </td>
                    <td className="px-3.5 py-2.5 text-center">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRowClick?.(row.currency);
                        }}
                        className="text-[11px] font-medium text-accent hover:underline"
                      >
                        Details
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default ConsensusDataTable;
