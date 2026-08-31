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
  dca: "DCA",
};

export function kindLabel(kind: string | undefined): string {
  if (!kind) return LONG_SHORT_KIND;
  return KIND_LABELS[kind as StrategyKind] ?? kind.replace(/_/g, " ");
}

export function inferKind(strategyId: string, explicit?: string): StrategyKind {
  if (explicit && explicit in KIND_LABELS) return explicit as StrategyKind;
  if (strategyId.includes("slapper")) return "long_short";
  return "long_short";
}
