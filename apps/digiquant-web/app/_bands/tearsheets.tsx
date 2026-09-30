import { Band } from "../_chrome/Band";
import { StrategyRailLive } from "@/components/tearsheet/rail/strategy-rail-live";

export function TearsheetsBand() {
  return (
    <Band
      id="tearsheets"
      title="Tearsheets"
      takeaway="Backtest results per strategy. In-sample and illustrative, labelled as such."
      status="backtest only"
    >
      <StrategyRailLive />
    </Band>
  );
}
