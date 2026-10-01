import { Band } from "../_chrome/Band";
import { StrategyRailLive } from "@/components/tearsheet/rail/strategy-rail-live";

export function TearsheetsBand() {
  return (
    <Band
      id="tearsheets"
      title="Tearsheets"
      takeaway="Every strategy ends in a backtest tearsheet, as the dashboard lists them. Results are in-sample and illustrative."
      status="backtest only"
    >
      <StrategyRailLive />
    </Band>
  );
}
