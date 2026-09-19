'use client';

import { useMemo, useState } from 'react';
import {
  Button,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
} from '@digithings/ui/ui';
import { SegmentedControl } from '@digithings/ui';
import {
  LEAN_BAND,
  STRONG_BAND,
  currencyColor,
  scoreColorClass,
  scoreLabel,
} from '@/lib/twelve-x/consensus-bar';
import type { ConsensusDeltaSet, FxConsensusDivergence, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { deriveConsensusRows, type ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import { fmtNEff, fmtSigned } from '@/lib/twelve-x/format';
import { ConsensusScoreBar } from './ConsensusScoreBars';
import DeltaChip from './DeltaChip';
import DivergenceChip from './DivergenceChip';

export type RowFilter = 'all' | 'bullish' | 'bearish' | 'strong';
export type SortDir = 'asc' | 'desc';
export type SortKey =
  | 'currency'
  | 'actualNow'
  | 'avgNow'
  | 'priorChange'
  | 'n_views'
  | 'agreement'
  | 'confidence'
  | 'n_eff';

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

export interface ConsensusDataTableProps {
  series: FxConsensusSnapshotRow[];
  latest: FxConsensusSnapshotRow[];
  deltas: ConsensusDeltaSet;
  divergenceByCurrency?: Record<string, FxConsensusDivergence>;
  onDivergenceClick?: (ccy: string) => void;
  onRowClick?: (ccy: string) => void;
  initialFilter?: RowFilter;
}

export function ConsensusDataTable({
  series,
  latest,
  deltas,
  divergenceByCurrency = {},
  onDivergenceClick,
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
      const av = (sortKey === 'n_views' || sortKey === 'agreement' || sortKey === 'confidence' || sortKey === 'n_eff')
        ? (latestByRow.get(a.currency)?.[sortKey] ?? null)
        : a[sortKey];
      const bv = (sortKey === 'n_views' || sortKey === 'agreement' || sortKey === 'confidence' || sortKey === 'n_eff')
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
      <Card data-reveal className="gap-0 p-8 text-center text-sm text-ink-mute">
        No consensus data available.
      </Card>
    );
  }

  return (
    <div className="space-y-3.5">
      <SegmentedControl
        options={FILTERS.map((f) => ({ value: f.key, label: f.label }))}
        value={filter}
        onChange={setFilter}
        dress="accent"
        aria-label="Filter rows"
      />

      <Card data-reveal className="gap-0 overflow-hidden p-0">
        <Table className="min-w-[880px]">
          <TableHeader>
            <TableRow>
              <TableHead className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('currency')}
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  Currency
                </Button>
              </TableHead>
              <TableHead numeric className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('actualNow')}
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  Current
                </Button>
              </TableHead>
              <TableHead numeric className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('avgNow')}
                  title="Trailing 5-run average"
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  Average
                </Button>
              </TableHead>
              <TableHead numeric className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('priorChange')}
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  Prior Δ
                </Button>
              </TableHead>
              <TableHead numeric className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('n_views')}
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  Opinions
                </Button>
              </TableHead>
              <TableHead numeric className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('agreement')}
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  Agreement
                </Button>
              </TableHead>
              <TableHead numeric className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('confidence')}
                  title="Relevance-weighted conviction share"
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  Conf
                </Button>
              </TableHead>
              <TableHead numeric className="h-auto px-3.5 py-2.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  onClick={() => onHeaderClick('n_eff')}
                  title="Effective sample size"
                  className="h-auto gap-0 p-0 text-[10px] font-semibold uppercase tracking-wider hover:bg-transparent"
                >
                  n_eff
                </Button>
              </TableHead>
              <TableHead className="h-auto px-3.5 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                Score
              </TableHead>
              <TableHead className="h-auto px-3.5 py-2.5 text-center text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                Bias
              </TableHead>
              <TableHead className="h-auto px-3.5 py-2.5 text-center text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
                Details
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const latestRow = latestByRow.get(row.currency);
              const score = row.actualNow ?? 0;
              const colorClass = scoreColorClass(score);
              const n_views = latestRow?.n_views ?? 0;
              const agreement = latestRow?.agreement ?? 0;
              const divergence = divergenceByCurrency[row.currency];
              return (
                <TableRow
                  key={row.currency}
                  data-ccy={row.currency}
                  onClick={() => onRowClick?.(row.currency)}
                  interactive
                  className="text-sm hover:bg-ink/[0.02]"
                >
                  <TableRowHeader className="px-3.5 py-2.5">
                    <span
                      className="font-mono font-semibold text-[13px]"
                      style={{ color: currencyColor(row.currency) }}
                    >
                      {row.currency}
                    </span>
                  </TableRowHeader>
                  <TableCell numeric className={`px-3.5 py-2.5 font-mono text-[13px] ${colorClass}`}>
                    {fmtSigned(row.actualNow)}
                  </TableCell>
                  <TableCell numeric className="px-3.5 py-2.5 font-mono text-[13px] text-ink-soft">
                    {fmtSigned(row.avgNow)}
                  </TableCell>
                  <TableCell numeric className="px-3.5 py-2.5 font-mono text-[13px] text-ink-soft">
                    {fmtSigned(row.priorChange)}
                  </TableCell>
                  <TableCell numeric className="px-3.5 py-2.5 font-mono text-[13px] text-ink-soft">
                    {n_views}
                  </TableCell>
                  <TableCell numeric className="px-3.5 py-2.5 font-mono text-[13px] text-ink-soft">
                    {agreement !== null && Number.isFinite(agreement) ? `${Math.round(agreement * 100)}%` : '—'}
                  </TableCell>
                  <TableCell numeric className="px-3.5 py-2.5 font-mono text-[13px] text-ink-soft">
                    {(() => {
                      const confidence = latestRow?.confidence ?? null;
                      return confidence !== null && Number.isFinite(confidence)
                        ? `${Math.round(confidence * 100)}%`
                        : '—';
                    })()}
                  </TableCell>
                  <TableCell numeric className="px-3.5 py-2.5 font-mono text-[13px] text-ink-soft">
                    {fmtNEff(latestRow?.n_eff)}
                  </TableCell>
                  <TableCell className="px-3.5 py-2.5">
                    <div className="flex min-w-[120px]">
                      <ConsensusScoreBar value={score} />
                    </div>
                  </TableCell>
                  <TableCell className="px-3.5 py-2.5 text-center">
                    {divergence?.isDivergent ? (
                      <DivergenceChip
                        gap={divergence.gap}
                        onClick={() => onDivergenceClick?.(row.currency)}
                      />
                    ) : (
                      <span className="font-mono text-[11px] text-ink-mute">—</span>
                    )}
                  </TableCell>
                  <TableCell className="px-3.5 py-2.5 text-center">
                    <Button
                      type="button"
                      variant="link"
                      size="xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRowClick?.(row.currency);
                      }}
                      className="h-auto gap-0 p-0 text-[11px] font-medium text-accent"
                    >
                      Details
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

export default ConsensusDataTable;
