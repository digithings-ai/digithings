/**
 * Homepage strategy-deck slot after the live index resolves.
 *
 * Skeleton is only for the in-flight fetch. An unpublished slug (btc_sdca with
 * no strategy_tearsheets row) must not stay a KPI skeleton — that looks like a
 * loaded empty tearsheet (#3447).
 */
export type SuiteSlotState = "skeleton" | "ready" | "unpublished";

export function suiteSlotState(
  indexResolved: boolean,
  entry: { strategy: string } | undefined,
): SuiteSlotState {
  if (!indexResolved) return "skeleton";
  return entry ? "ready" : "unpublished";
}