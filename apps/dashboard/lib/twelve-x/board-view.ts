/**
 * Pure view-model for the consensus board (Today) and the small-multiples grid
 * (Consensus). One row per currency in canonical order, built on the shared
 * `deriveConsensusRows` so the trailing-average headline can never drift from
 * the Consensus tab, plus the pieces the visual marks need: a raw per-run
 * history for the sparkline and the latest stance mix for the share bar.
 */
import type { FxConsensusSnapshotRow } from './types';
import { deriveConsensusRows, type ConsensusCurrencyRow } from './consensus-view';
import { fmtSigned } from './format';

/** A trend needs at least this many finite runs; fewer shows a dash, not a fake flat line. */
export const MIN_TREND_RUNS = 5;
/** History window drawn per currency. */
export const HISTORY_RUNS = 30;

export interface StanceMix {
  bullish: number;
  bearish: number;
  neutral: number;
  watch: number;
}

export interface BoardRow extends ConsensusCurrencyRow {
  /** Raw per-run scores, oldest first, `null` where a run has no finite score. */
  history: Array<number | null>;
  /** True when the history has enough finite runs to draw a trend. */
  hasTrend: boolean;
  /** Latest run's stance mix, or `null` when the source row carries none. */
  stance: StanceMix | null;
  nBrokers: number | null;
  /** run_date of the latest row for the currency. */
  latestRun: string | null;
}

function finiteOrNull(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

/** Stance mix from one snapshot row; `null` when no bucket is positive. */
export function stanceFromRow(row: FxConsensusSnapshotRow | undefined): StanceMix | null {
  if (!row) return null;
  const pick = (v: number) => (Number.isFinite(v) && v > 0 ? v : 0);
  const mix: StanceMix = {
    bullish: pick(row.bullish_pct),
    bearish: pick(row.bearish_pct),
    neutral: pick(row.neutral_pct),
    watch: pick(row.watch_pct),
  };
  return mix.bullish + mix.bearish + mix.neutral + mix.watch > 0 ? mix : null;
}

export function deriveBoardRows(series: FxConsensusSnapshotRow[]): BoardRow[] {
  const base = deriveConsensusRows(series);
  return base.map((row) => {
    // One row per run_date (last write wins), oldest first.
    const byDate = new Map<string, FxConsensusSnapshotRow>();
    for (const r of series) if (r.currency === row.currency) byDate.set(r.run_date, r);
    const ordered = [...byDate.values()].sort((a, b) => a.run_date.localeCompare(b.run_date));
    const windowed = ordered.slice(-HISTORY_RUNS);
    const history = windowed.map((r) => finiteOrNull(r.score));
    const latest = ordered[ordered.length - 1];
    return {
      ...row,
      history,
      hasTrend: history.filter((v) => v !== null).length >= MIN_TREND_RUNS,
      stance: stanceFromRow(latest),
      nBrokers: finiteOrNull(latest?.n_brokers),
      latestRun: latest?.run_date ?? null,
    };
  });
}

/** One-sentence text alternative for the whole board (screen readers). */
export function boardSummary(rows: BoardRow[]): string {
  if (rows.length === 0) return 'Consensus board: no consensus history yet.';
  const parts = rows.map((r) => `${r.currency} ${fmtSigned(r.avgNow)} (${r.label.toLowerCase()})`);
  return `Consensus board, trailing 5-run average per currency: ${parts.join(', ')}.`;
}

/** Stance mix as CompositionBar segments (bull/bear use accent/warn; never up/down). */
export function stanceSegments(mix: StanceMix | null) {
  if (!mix) return [];
  return [
    { key: 'bullish', label: 'Bullish', value: mix.bullish, tone: 'accent' as const },
    { key: 'bearish', label: 'Bearish', value: mix.bearish, tone: 'warn' as const },
    { key: 'watch', label: 'Watch', value: mix.watch, tone: 'soft' as const },
    { key: 'neutral', label: 'Neutral', value: mix.neutral, tone: 'mute' as const },
  ];
}
