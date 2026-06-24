'use client';

import { useMemo, useState } from 'react';
import { consensusAverageAt, type ScorePoint } from '@/lib/twelve-x/consensus-derive';
import {
  LEAN_BAND,
  STRONG_BAND,
  currencyColor,
  scoreColorClass,
  scoreLabel,
} from '@/lib/twelve-x/consensus-bar';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { ConsensusScoreBar } from './ConsensusScoreBars';
import DeltaChip from './DeltaChip';

/**
 * The Consensus page's rich, sortable G10 data table (frozen visual-spec
 * redesign #2 — the "Consensus — G10" table that now leads the Consensus tab).
 *
 * Columns: Ccy · score bar · Consensus · Δ prior · Avg (selectable trailing
 * window) · vs Avg · Conf% · Agree% · Signal. The averaging window (3/5/10/20
 * runs, default 5) recomputes the Avg and vs-Avg columns live. Quick filter
 * chips (All / Bullish / Bearish / Strong) and clickable sortable headers round
 * it out. All bar math, colors and labels come from the shared Phase 1 helpers.
 */

/** The available trailing-average windows (runs), matching the spec's segment. */
export const AVG_WINDOWS = [3, 5, 10, 20] as const;
export type AvgWindow = (typeof AVG_WINDOWS)[number];

/** A quick-filter bucket over the latest score. */
export type RowFilter = 'all' | 'bullish' | 'bearish' | 'strong';

/** The sort direction. */
export type SortDir = 'asc' | 'desc';

/** Sortable column keys (the score bar is presentational / non-sortable). */
export type SortKey =
  | 'currency'
  | 'score'
  | 'scoreDelta'
  | 'avg'
  | 'vs'
  | 'confidence'
  | 'agreement'
  | 'signal';

/** Which side of the windowed average the latest score sits on. */
export type VsAvgFlag = 'above' | 'below' | 'equal';

/** One assembled table row (the view-model the helpers sort + render). */
export interface ConsensusTableRow {
  currency: string;
  /** Latest raw consensus score for the currency. */
  score: number;
  /** Δ vs the immediately prior run (from the delta set); null when unknown. */
  scoreDelta: number | null;
  /** Trailing-window mean of the currency's score series; null when underivable. */
  avg: number | null;
  /** Latest score relative to the windowed average; null when either is missing. */
  vs: VsAvgFlag | null;
  confidence: number;
  agreement: number;
  /** Human conviction label derived from the latest score. */
  signal: string;
}

/** Sub-epsilon gaps count as flat (mirrors the spec's `< 0.005` tolerance). */
const EPS = 0.005;

/**
 * Trailing-window mean of one currency's score series.
 *
 * Groups `series` to the given `currency`, sorts ascending by `run_date`, and
 * takes the mean of the last `window` finite scores (via the shared
 * `consensusAverageAt`, which skips non-finite points). Returns `null` when the
 * currency has no derivable points.
 */
export function avgWindow(
  series: FxConsensusSnapshotRow[],
  currency: string,
  window: number,
): number | null {
  const points: ScorePoint[] = series
    .filter((r) => r.currency === currency)
    .sort((a, b) => a.run_date.localeCompare(b.run_date))
    .map((r) => ({ score: r.score }));
  if (points.length === 0) return null;
  return consensusAverageAt(points, points.length - 1, window);
}

/**
 * Compare a currency's latest actual score against its windowed average.
 * Returns `null` when either input is missing or non-finite, otherwise
 * `'above'` / `'below'` / `'equal'` (a sub-epsilon gap is `'equal'`).
 */
export function vsAvg(actual: number | null, avg: number | null): VsAvgFlag | null {
  if (actual === null || avg === null) return null;
  if (!Number.isFinite(actual) || !Number.isFinite(avg)) return null;
  const gap = actual - avg;
  if (Math.abs(gap) < EPS) return 'equal';
  return gap > 0 ? 'above' : 'below';
}

/** Lexical sort keys; everything else compares numerically. */
const LEXICAL_KEYS: ReadonlySet<SortKey> = new Set<SortKey>(['currency', 'signal']);

/** Numeric field accessor for the non-lexical sort keys. */
function numericValue(row: ConsensusTableRow, key: SortKey): number | null {
  switch (key) {
    case 'score':
      return row.score;
    case 'scoreDelta':
      return row.scoreDelta;
    case 'avg':
      return row.avg;
    case 'vs':
      // Order by the actual gap so vs-Avg sorts the way the arrows read.
      return row.avg === null ? null : row.score - row.avg;
    case 'confidence':
      return row.confidence;
    case 'agreement':
      return row.agreement;
    default:
      return null;
  }
}

/**
 * Stable sort of table rows by a column key + direction.
 *
 * Lexical keys (`currency`, `signal`) compare with `localeCompare`; all other
 * keys compare numerically with `null`s ordered last in BOTH directions (a
 * missing average should never crowd the top of either ordering). Does not
 * mutate the input array.
 */
export function sortRows(
  rows: ConsensusTableRow[],
  key: SortKey,
  dir: SortDir,
): ConsensusTableRow[] {
  const mul = dir === 'asc' ? 1 : -1;
  // Decorate with the original index so ties preserve input order (stable).
  return rows
    .map((row, i) => ({ row, i }))
    .sort((a, b) => {
      let cmp: number;
      if (LEXICAL_KEYS.has(key)) {
        const av = String(a.row[key as 'currency' | 'signal']);
        const bv = String(b.row[key as 'currency' | 'signal']);
        cmp = mul * av.localeCompare(bv);
      } else {
        const av = numericValue(a.row, key);
        const bv = numericValue(b.row, key);
        // Nulls always sort last regardless of direction.
        if (av === null && bv === null) cmp = 0;
        else if (av === null) cmp = 1;
        else if (bv === null) cmp = -1;
        else cmp = mul * (av - bv);
      }
      return cmp !== 0 ? cmp : a.i - b.i;
    })
    .map((d) => d.row);
}

interface ColumnDef {
  key: SortKey | 'bar';
  label: string;
  align: 'left' | 'right';
  sortable: boolean;
}

const COLUMNS: ColumnDef[] = [
  { key: 'currency', label: 'Ccy', align: 'left', sortable: true },
  { key: 'bar', label: 'Score bar', align: 'left', sortable: false },
  { key: 'score', label: 'Consensus', align: 'right', sortable: true },
  { key: 'scoreDelta', label: 'Δ prior', align: 'right', sortable: true },
  { key: 'avg', label: 'Avg', align: 'right', sortable: true },
  { key: 'vs', label: 'vs Avg', align: 'right', sortable: true },
  { key: 'confidence', label: 'Conf', align: 'right', sortable: true },
  { key: 'agreement', label: 'Agree', align: 'right', sortable: true },
  { key: 'signal', label: 'Signal', align: 'left', sortable: true },
];

const FILTERS: { key: RowFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'bullish', label: 'Bullish' },
  { key: 'bearish', label: 'Bearish' },
  { key: 'strong', label: 'Strong' },
];

/**
 * Quick-filter predicate over a row's latest score.
 *
 * `bullish` keeps scores at/above the lean band (`>= LEAN_BAND`); `bearish`
 * keeps scores at/below the negative lean band (`<= -LEAN_BAND`); `strong`
 * keeps either-sign strong convictions (`|s| >= STRONG_BAND`); `all` keeps
 * everything. Exported so the band boundaries are unit-testable directly.
 */
export function passesFilter(row: ConsensusTableRow, filter: RowFilter): boolean {
  if (filter === 'bullish') return row.score >= LEAN_BAND;
  if (filter === 'bearish') return row.score <= -LEAN_BAND;
  if (filter === 'strong') return Math.abs(row.score) >= STRONG_BAND;
  return true;
}

/** Format a score as a signed 2-dp string, or an em dash for null/non-finite. */
function fmtSigned(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

/** Format a [0,1] ratio as a whole-percent string, or em dash if non-finite. */
function fmtPct(v: number): string {
  return Number.isFinite(v) ? `${Math.round(v * 100)}%` : '—';
}

/** vs-Avg flag → arrow glyph + directional color class. */
function vsPresentation(flag: VsAvgFlag | null): { arrow: string; cls: string } {
  if (flag === 'above') return { arrow: '▲', cls: 'text-fin-green' };
  if (flag === 'below') return { arrow: '▼', cls: 'text-fin-red' };
  return { arrow: '·', cls: 'text-text-muted' };
}

export interface ConsensusDataTableProps {
  /** Per-currency consensus time series (one row per currency per run_date). */
  series: FxConsensusSnapshotRow[];
  /** Latest snapshot per currency (the row the table summarizes). */
  latest: FxConsensusSnapshotRow[];
  /** Run-over-run deltas (drives the Δ-prior chip). */
  deltas: ConsensusDeltaSet;
  /** "Why this weight?" cross-link: open the ledger filtered to a currency. */
  onDrillToLedger?: (ccy: string) => void;
  /** Initial quick-filter bucket (All default). Exposed for deterministic SSR tests. */
  initialFilter?: RowFilter;
}

export function ConsensusDataTable({
  series,
  latest,
  deltas,
  onDrillToLedger,
  initialFilter = 'all',
}: ConsensusDataTableProps) {
  const [window, setWindow] = useState<AvgWindow>(5);
  const [filter, setFilter] = useState<RowFilter>(initialFilter);
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  // Latest score per currency, in canonical G10 order (extras sorted after).
  const ordered = useMemo<FxConsensusSnapshotRow[]>(() => {
    const byCcy = new Map<string, FxConsensusSnapshotRow>();
    for (const r of latest) byCcy.set(r.currency, r);
    const present = [...byCcy.keys()];
    const head = G10_CURRENCIES.filter((c) => byCcy.has(c));
    const headSet = new Set<string>(head);
    const extras = present.filter((c) => !headSet.has(c)).sort();
    return [...head, ...extras].map((c) => byCcy.get(c) as FxConsensusSnapshotRow);
  }, [latest]);

  // Assemble + filter + sort the view-model. Recomputes when the window changes.
  const rows = useMemo<ConsensusTableRow[]>(() => {
    const built = ordered.map((r) => {
      const score = Number.isFinite(r.score) ? r.score : 0;
      const avg = avgWindow(series, r.currency, window);
      const cDelta = deltas.byCurrency[r.currency];
      return {
        currency: r.currency,
        score,
        scoreDelta: cDelta?.scoreDelta ?? null,
        avg,
        vs: vsAvg(score, avg),
        confidence: r.confidence,
        agreement: r.agreement,
        signal: scoreLabel(score),
      } satisfies ConsensusTableRow;
    });
    const filtered = built.filter((row) => passesFilter(row, filter));
    return sortRows(filtered, sortKey, sortDir);
  }, [ordered, series, deltas, window, filter, sortKey, sortDir]);

  const hasData = ordered.length > 0;

  function onHeaderClick(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Currencies/labels read best ascending; numbers default to descending.
      setSortDir(key === 'currency' || key === 'signal' ? 'asc' : 'desc');
    }
  }

  if (!hasData) {
    return (
      <div className="glass-card p-8 text-center text-text-muted text-sm">
        No consensus snapshot available yet.
      </div>
    );
  }

  return (
    <div className="space-y-3.5">
      {/* Controls: averaging window */}
      <div className="flex items-center gap-2.5 flex-wrap">
        <span className="text-[11px] uppercase tracking-wider text-text-muted">
          Avg window
        </span>
        <div
          className="inline-flex rounded-lg border border-border-subtle overflow-hidden"
          role="group"
          aria-label="Averaging window"
        >
          {AVG_WINDOWS.map((n, idx) => {
            const on = window === n;
            return (
              <button
                key={n}
                type="button"
                data-n={n}
                aria-pressed={on}
                onClick={() => setWindow(n)}
                className={`px-3 py-1.5 text-[11.5px] font-medium tabular-nums transition-colors ${
                  idx < AVG_WINDOWS.length - 1 ? 'border-r border-border-subtle' : ''
                } ${
                  on
                    ? 'bg-fin-blue/15 text-fin-blue'
                    : 'text-text-secondary hover:text-text-primary hover:bg-white/[0.03]'
                }`}
              >
                {n}
              </button>
            );
          })}
        </div>
        <span className="text-[11px] text-text-muted ml-1">
          trailing-{window}-run consensus average
        </span>
      </div>

      {/* Quick filters */}
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
                  ? 'border-fin-blue/40 bg-fin-blue/15 text-fin-blue'
                  : 'border-border-subtle text-text-muted hover:text-text-primary'
              }`}
            >
              {f.label}
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="glass-card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse">
            <thead>
              <tr className="border-b border-border-subtle">
                {COLUMNS.map((c) => {
                  const isSorted = c.sortable && c.key === sortKey;
                  const ind = isSorted ? (sortDir === 'desc' ? '▼' : '▲') : '';
                  const alignCls = c.align === 'right' ? 'text-right' : 'text-left';
                  if (!c.sortable) {
                    return (
                      <th
                        key={c.key}
                        className={`px-3.5 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted ${alignCls}`}
                      >
                        {c.label}
                      </th>
                    );
                  }
                  return (
                    <th
                      key={c.key}
                      aria-sort={
                        isSorted ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'
                      }
                      className={`px-3.5 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted ${alignCls}`}
                    >
                      <button
                        type="button"
                        data-key={c.key}
                        onClick={() => onHeaderClick(c.key as SortKey)}
                        className={`inline-flex items-center gap-1 uppercase tracking-wider hover:text-text-primary transition-colors ${
                          isSorted ? 'text-text-primary' : ''
                        }`}
                      >
                        {c.label}
                        {ind ? <span className="text-fin-blue text-[9px]">{ind}</span> : null}
                      </button>
                    </th>
                  );
                })}
                {onDrillToLedger ? (
                  <th className="px-3.5 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted text-right">
                    Trace
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {rows.map((r) => {
                const colorClass = scoreColorClass(r.score);
                const cDelta = deltas.byCurrency[r.currency];
                const isNew =
                  cDelta != null && cDelta.scoreDelta == null && cDelta.prevRunDate == null;
                const vsP = vsPresentation(r.vs);
                return (
                  <tr
                    key={r.currency}
                    data-ccy={r.currency}
                    className="text-sm hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-3.5 py-2.5">
                      <span
                        className="font-mono font-semibold text-[13px]"
                        style={{ color: currencyColor(r.currency) }}
                      >
                        {r.currency}
                      </span>
                    </td>
                    <td className="px-3.5 py-2.5">
                      <div className="flex min-w-[120px]">
                        <ConsensusScoreBar value={r.score} />
                      </div>
                    </td>
                    <td
                      className={`px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] ${colorClass}`}
                    >
                      {fmtSigned(r.score)}
                    </td>
                    <td className="px-3.5 py-2.5 text-right">
                      <DeltaChip delta={r.scoreDelta} isNew={isNew} />
                    </td>
                    <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] text-text-secondary">
                      {r.avg === null ? '—' : r.avg.toFixed(2)}
                    </td>
                    <td
                      className={`px-3.5 py-2.5 text-right font-mono tabular-nums text-[12.5px] ${vsP.cls}`}
                      title="Latest score vs the windowed consensus average"
                    >
                      {r.vs === null ? '—' : `${vsP.arrow} ${fmtSigned(r.score - (r.avg as number))}`}
                    </td>
                    <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] text-text-secondary">
                      {fmtPct(r.confidence)}
                    </td>
                    <td className="px-3.5 py-2.5 text-right font-mono tabular-nums text-[13px] text-text-secondary">
                      {fmtPct(r.agreement)}
                    </td>
                    <td className={`px-3.5 py-2.5 text-[12px] font-medium ${colorClass}`}>
                      {r.signal}
                    </td>
                    {onDrillToLedger ? (
                      <td className="px-3.5 py-2.5 text-right">
                        <button
                          type="button"
                          onClick={() => onDrillToLedger(r.currency)}
                          className="text-[11px] font-medium text-fin-blue hover:underline"
                          title={`Why this weight? Open the relevance ledger filtered to ${r.currency}`}
                        >
                          Why?
                        </button>
                      </td>
                    ) : null}
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
