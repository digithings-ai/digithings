import { inferPublicType, publicTypeLabel } from "./strategy-kinds";

/** Type chip / subtitle — SDCA, L/S, RS. Unknown types still render. */
export function StrategyTypeChip({
  strategy,
  kind,
  className = "ts-chip ts-chip-soft",
}: {
  strategy: string;
  kind?: string;
  className?: string;
}) {
  const type = inferPublicType(strategy, kind);
  return <span className={className}>{publicTypeLabel(type)}</span>;
}
