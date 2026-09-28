/** Strategy taxonomy for library filters (extensible as the catalog grows). */

import {
  LONG_ONLY_KIND,
  LONG_SHORT_KIND,
  SHORT_ONLY_KIND,
} from "./direction-label";

export type StrategyKind =
  | "long_short"
  | "long_only"
  | "short_only"
  | "relative_strength"
  | "rotation"
  | "dca";

export const KIND_LABELS: Record<StrategyKind, string> = {
  long_short: LONG_SHORT_KIND,
  long_only: LONG_ONLY_KIND,
  short_only: SHORT_ONLY_KIND,
  relative_strength: "Relative strength",
  rotation: "Rotation",
  dca: "Remaining-book DCA",
};

/** Public catalog types — asset-then-type names (BTC-SDCA, BTC L/S). RS is reserved. */
export const PUBLIC_STRATEGY_TYPES = ["sdca", "long_short", "relative_strength"] as const;
export type PublicStrategyType = (typeof PUBLIC_STRATEGY_TYPES)[number];

export const PUBLIC_TYPE_LABELS: Record<PublicStrategyType, string> = {
  sdca: "SDCA",
  long_short: "L/S",
  relative_strength: "RS",
};

export type PublicTypeFilter = "all" | PublicStrategyType;

export function kindLabel(kind: string | undefined): string {
  if (!kind) return LONG_SHORT_KIND;
  return KIND_LABELS[kind as StrategyKind] ?? kind.replace(/_/g, " ");
}

export function inferKind(strategyId: string, explicit?: string): StrategyKind {
  if (explicit && explicit in KIND_LABELS) return explicit as StrategyKind;
  if (strategyId.includes("sdca") || /(?:^|_)dca(?:_|$)/.test(strategyId)) return "dca";
  if (strategyId.includes("slapper")) return "long_short";
  return "long_short";
}

/** Map a catalog entry onto a public type. Unknown kinds still render as-is. */
export function inferPublicType(strategyId: string, kind?: string): string {
  if (strategyId.includes("sdca") || kind === "dca") return "sdca";
  if (kind === "relative_strength" || strategyId.includes("rs_")) return "relative_strength";
  if (strategyId.includes("slapper") || kind === "long_short") return "long_short";
  if (kind && PUBLIC_STRATEGY_TYPES.includes(kind as PublicStrategyType)) return kind;
  return kind || "long_short";
}

export function publicTypeLabel(type: string): string {
  if (type in PUBLIC_TYPE_LABELS) return PUBLIC_TYPE_LABELS[type as PublicStrategyType];
  return type.replace(/_/g, " ");
}

/** Types currently offered as filter chips. Append `relative_strength` when an RS book ships. */
const FILTER_TYPES: readonly PublicStrategyType[] = ["sdca", "long_short"];

/** Filter chips: All plus the shipped public types (RS stays on the enum until a book uses it). */
export function publicTypeFilterOptions(): { value: PublicTypeFilter; label: string }[] {
  return [
    { value: "all", label: "All" },
    ...FILTER_TYPES.map((t) => ({ value: t, label: PUBLIC_TYPE_LABELS[t] })),
  ];
}

export function matchesPublicType(
  strategyId: string,
  kind: string | undefined,
  filter: PublicTypeFilter,
): boolean {
  if (filter === "all") return true;
  return inferPublicType(strategyId, kind) === filter;
}

/**
 * Tearsheet Charts → Indicators is an SDCA surface (composite risk extras).
 * L/S P/L books never get the tab — gate on public type, not empty series.
 */
export function showsIndicatorsTab(strategyId: string, kind?: string): boolean {
  return inferPublicType(strategyId, kind) === "sdca";
}
