import type { RebalanceAction } from '@/lib/types';
import { isMaterialRebalanceAction } from '@/lib/rebalance-actions';

/**
 * Compact book-move copy for the Brief decision summary.
 *
 * Assembled only from existing rebalance fields — no LLM calls, no invented
 * metrics. The hero builder this file used to carry (`buildBriefHighlight`)
 * went away with the Brief's "Your update" hero in Q3b slice 2 (#4443); what
 * remains are the two helpers `DailyBriefWorkspace` still renders.
 */

const MAX_LINE = 140;

function clip(text: string, max = MAX_LINE): string {
  const trimmed = text.replace(/\s+/g, ' ').trim();
  if (trimmed.length <= max) return trimmed;
  const cut = trimmed.slice(0, max - 1);
  const at = cut.lastIndexOf(' ');
  return `${(at > 40 ? cut.slice(0, at) : cut).trimEnd()}…`;
}

function titleCaseAction(action: string): string {
  const kind = action.trim().toUpperCase();
  if (!kind) return 'Adjust';
  return kind.charAt(0) + kind.slice(1).toLowerCase();
}

/** Non-HOLD book moves (EXIT at 0% current weight is a no-op). */
export function activeRebalanceActions(actions: RebalanceAction[]): RebalanceAction[] {
  return actions.filter(isMaterialRebalanceAction);
}

/** Compact book move — action + ticker (+ weight delta). No thesis prose. */
export function portfolioActionChip(action: RebalanceAction): string {
  const verb = titleCaseAction(action.action);
  const ticker = action.ticker.trim().toUpperCase();
  const from = action.current_pct;
  const to = action.recommended_pct;
  if (Number.isFinite(from) && Number.isFinite(to) && from !== to) {
    return clip(`${verb} ${ticker} (${from.toFixed(1)}% → ${to.toFixed(1)}%)`);
  }
  return clip(`${verb} ${ticker}`);
}
