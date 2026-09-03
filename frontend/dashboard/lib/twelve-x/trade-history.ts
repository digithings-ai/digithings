/**
 * Pure assembly for the Trades history table: full idea rows joined to
 * lifecycle eval rows. Close-based verdicts only — excursion (bias) and
 * level-touch verdicts arrive with the high/low feed + eval migration.
 */
import type { FxIdeaEvalRow, FxLevelProvenance, FxTradeIdeaRow } from './types';
import { formatLevelValue, hasTradeLevels, parseTradeLevels } from './trade-levels';

export type TradeLifecycle = 'live' | 'closed' | 'no_data' | 'unscored';

export interface TradeHistoryRow {
  runDate: string;
  rank: number;
  pair: string;
  direction: string;
  title: string;
  catalyst: string;
  entryBand: string | null;
  stop: string | null;
  target: string | null;
  hasLevels: boolean;
  lifecycle: TradeLifecycle;
  entryDate: string | null;
  exitDate: string | null;
  sessions: number | null;
  holdReturn: number | null;
  directionalWin: boolean | null;
}

function evalKey(runDate: string, rank: number): string {
  return `${runDate}::${rank}`;
}

function lifecycleOf(status: string | undefined): TradeLifecycle {
  if (!status) return 'unscored';
  if (status === 'open') return 'live';
  if (status === 'missing_rates') return 'no_data';
  return 'closed';
}

/** Signed hold return as a one-decimal percent, or an em dash when unknown. */
export function formatHoldPct(holdReturn: number | null | undefined): string {
  if (holdReturn === null || holdReturn === undefined || !Number.isFinite(holdReturn)) {
    return '—';
  }
  const pct = holdReturn * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

export function assembleTradeHistory(
  ideas: FxTradeIdeaRow[],
  ideaEval: FxIdeaEvalRow[],
): TradeHistoryRow[] {
  const evalByKey = new Map(ideaEval.map((r) => [evalKey(r.run_date, r.rank), r]));
  return ideas
    .map((idea) => {
      const ev = evalByKey.get(evalKey(idea.run_date, idea.rank));
      const tl = parseTradeLevels(idea.trade_levels);
      const fmt = (value: string, provenance?: FxLevelProvenance) =>
        formatLevelValue(value, idea.pair, provenance);
      const entryBand =
        tl?.entry_low && tl?.entry_high
          ? `${fmt(tl.entry_low.value, tl.entry_low.provenance)}–${fmt(tl.entry_high.value, tl.entry_high.provenance)}`
          : (tl?.entry_low ?? tl?.entry_high)
            ? fmt(
                (tl.entry_low ?? tl.entry_high)?.value ?? '',
                (tl.entry_low ?? tl.entry_high)?.provenance,
              )
            : null;
      return {
        runDate: idea.run_date,
        rank: idea.rank,
        pair: idea.pair,
        direction: idea.direction,
        title: idea.title,
        catalyst: idea.catalyst,
        entryBand,
        stop: tl?.stop ? fmt(tl.stop.value, tl.stop.provenance) : null,
        target: tl && tl.targets.length > 0 ? fmt(tl.targets[0].value, tl.targets[0].provenance) : null,
        hasLevels: hasTradeLevels(tl),
        lifecycle: lifecycleOf(ev?.status),
        entryDate: ev?.entry_date ?? null,
        exitDate: ev?.exit_date ?? null,
        sessions: ev?.n_sessions ?? null,
        holdReturn: ev?.hold_return ?? ev?.ret ?? null,
        directionalWin: ev?.directional_win ?? ev?.hit ?? null,
      } satisfies TradeHistoryRow;
    })
    .sort((a, b) => b.runDate.localeCompare(a.runDate) || a.rank - b.rank);
}
