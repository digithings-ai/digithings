import { buildStrategyTearsheet, seriesSparkline } from "../../../../packages/ui/src/components/finance-tearsheet/strategy-sheet-model";
import { DASH } from "../read";

/** Tearsheet pane body. Unpublished figures are an em dash. No lecture. */
export type StrategySheetBody = {
  type: "sheet";
  rows: { label: string; value: string }[];
  chart: string | null;
  trades: string[][];
};

export function strategySheetBody(data: unknown): StrategySheetBody {
  const model = buildStrategyTearsheet(data, { title: "Tearsheet", symbol: "" });
  return {
    type: "sheet",
    rows: [...model.metrics, ...model.position].map((item) => ({ label: item.label, value: item.value ?? DASH })),
    chart: model.equity ? seriesSparkline(model.equity.map((point) => point.v)) : null,
    trades: model.trades?.rows ?? [],
  };
}
