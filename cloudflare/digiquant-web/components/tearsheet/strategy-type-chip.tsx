import { Badge } from "@digithings/web/ui";
import { inferPublicType, publicTypeLabel } from "./strategy-kinds";

/** Type chip / subtitle — SDCA, L/S, RS. Unknown types still render. */
export function StrategyTypeChip({
  strategy,
  kind,
  className,
}: {
  strategy: string;
  kind?: string;
  className?: string;
}) {
  const type = inferPublicType(strategy, kind);
  return (
    <Badge variant="outline" className={"text-ink-soft" + (className ? ` ${className}` : "")}>
      {publicTypeLabel(type)}
    </Badge>
  );
}
