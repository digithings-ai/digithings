import { MarketBarShell } from "../_chrome/MarketBarShell";
import { Band } from "../_chrome/Band";
import { StrategyRailLive } from "@/components/tearsheet/rail/strategy-rail-live";

/** Tearsheets: the live price strip sits here, above the strategies it prices,
 *  not in the page chrome. */
export function TearsheetsBand() {
  return (
    <Band
      id="tearsheets"
      title="Tearsheets"
      takeaway="Every strategy ends in a backtest tearsheet, as the dashboard lists them. Results are in-sample and illustrative."
      status="backtest only"
    >
      <div className="flex flex-col gap-4">
        <MarketBarShell />
        <StrategyRailLive />
      </div>
    </Band>
  );
}
