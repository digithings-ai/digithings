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
      takeaway="The tape is the live price feed. Each strategy ends in a backtest tearsheet. Unpublished statistics stay an em dash."
      status="backtest only"
    >
      <div className="flex min-w-0 flex-col gap-2">
        <MarketBarShell />
        <StrategyRailLive />
      </div>
    </Band>
  );
}
