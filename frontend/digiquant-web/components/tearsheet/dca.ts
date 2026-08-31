/**
 * Data-driven DCA / schema-1.3 helpers for the library card and tearsheet
 * (#3172). Drive off null KPIs and the `dca` / `vs_lump_pct` extras — never a
 * slug allowlist — so a future ETH book lights up without a frontend edit.
 */

import { inferKind } from "./strategy-kinds";
import type { StrategyIndexEntry, TearsheetData } from "./types";

/** Trade-based tiles apply only when the schema reports them as numbers. */
export function hasTradeKpis(
  winRatePct: number | null | undefined,
  profitFactor: number | null | undefined,
): boolean {
  return winRatePct != null && profitFactor != null;
}

export function isDcaTearsheet(data: Pick<TearsheetData, "dca" | "kind" | "strategy" | "win_rate_pct">): boolean {
  if (data.dca != null) return true;
  if (data.kind === "dca") return true;
  if (data.win_rate_pct == null && inferKind(data.strategy, data.kind) === "dca") return true;
  return inferKind(data.strategy, data.kind) === "dca";
}

export function isDcaIndexEntry(
  e: Pick<StrategyIndexEntry, "strategy" | "kind" | "vs_lump_pct" | "win_rate_pct">,
): boolean {
  if (e.vs_lump_pct != null) return true;
  return inferKind(e.strategy, e.kind) === "dca";
}
