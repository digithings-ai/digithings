"use client";

import { CONTEXT_BAR_CELLS } from "./digichat-context-meter-shares";
import { meterTone } from "./digichat-meter-tone";

export type UsageMeterValue = {
  /** Turns the visitor has spent. */
  used: number;
  /** Turns the gate currently allows: the free budget, or the unlocked one. */
  limit: number;
};

/**
 * The trial gate's turn budget as the segmented digichat cube bar.
 *
 * The bar sits in the composer toolbar where the context meter would be. It
 * is a gate number, not a token estimate: a tenant whose backend reports no
 * usage (a Foundry agent) still has a budget to show, and one that does
 * report usage still has turns that matter more than tokens.
 *
 * Shape: a small budget (the three free turns) gets one cell per turn, so
 * each turn is visible as a cell. A large one (the unlocked hundred) fills
 * the same 25-cell grid the context bar uses, proportionally. Both occupy the
 * same toolbar slot, so unlocking does not move the row.
 *
 * The fill is deliberately the used fraction: the bar starts empty and grows
 * as turns are spent, the way the context bar grows. Unlocking resets the
 * fraction because the denominator changes, which is the point of the
 * unlock, not a regression.
 */
export function usageBarShape(
  used: number,
  limit: number,
): { cells: number; lit: number } {
  // A non-finite count has no place on the bar; treat it as unspent rather
  // than letting NaN reach the aria-label or the cell count.
  const finite = (value: number): number =>
    Number.isFinite(value) ? value : 0;
  const safeLimit = Math.max(0, Math.floor(finite(limit)));
  const safeUsed = Math.max(0, Math.min(safeLimit, Math.floor(finite(used))));
  if (safeLimit === 0) return { cells: 0, lit: 0 };
  if (safeLimit <= CONTEXT_BAR_CELLS) {
    return { cells: safeLimit, lit: safeUsed };
  }
  // Never zero-lit while a turn has been spent: a proportional fill that
  // rounds to nothing would read as "no turns used". Never full until the
  // budget is: at 99/100 one cell stays dark, so a full bar always means
  // "no turns left".
  if (safeUsed === 0) return { cells: CONTEXT_BAR_CELLS, lit: 0 };
  if (safeUsed >= safeLimit) {
    return { cells: CONTEXT_BAR_CELLS, lit: CONTEXT_BAR_CELLS };
  }
  const proportional = Math.round((safeUsed / safeLimit) * CONTEXT_BAR_CELLS);
  return {
    cells: CONTEXT_BAR_CELLS,
    lit: Math.max(1, Math.min(CONTEXT_BAR_CELLS - 1, proportional)),
  };
}

export function DigichatUsageMeter({ usage }: { usage: UsageMeterValue }) {
  const { cells, lit } = usageBarShape(usage.used, usage.limit);
  if (cells === 0) return null;

  const finite = (value: number): number =>
    Number.isFinite(value) ? value : 0;
  const limit = Math.max(0, Math.floor(finite(usage.limit)));
  const used = Math.max(0, Math.min(limit, Math.floor(finite(usage.used))));
  const left = Math.max(0, limit - used);
  const tone = meterTone(limit > 0 ? used / limit : 0);

  return (
    <span className={`aui-context-meter-wrap aui-usage-meter-wrap ${tone}`.trim()}>
      <span
        className={`aui-context-meter aui-usage-meter ${tone}`.trim()}
        role="img"
        tabIndex={0}
        aria-label={`Turns: ${left} of ${limit} left`}
        data-testid="embed-usage-meter"
      >
        {Array.from({ length: cells }, (_, index) => (
          <span
            key={index}
            className={
              index < lit ? "aui-context-bar-cell is-usage" : "aui-context-bar-cell"
            }
          />
        ))}
      </span>
      <span className="aui-context-card" role="tooltip">
        <span className="aui-context-card-row aui-context-card-total">
          <span>Turns left</span>
          <span>{left}</span>
        </span>
        <span className="aui-context-card-row">
          <span>Used</span>
          <span>
            {used} / {limit}
          </span>
        </span>
      </span>
    </span>
  );
}
