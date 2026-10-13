import { MarketBarShell } from "../_chrome/MarketBarShell";
import { Band } from "../_chrome/Band";
import { StrategyRailLive } from "@/components/tearsheet/rail/strategy-rail-live";

/** Tearsheets: the live price strip and a compact strategy sheet, one box. */
export function TearsheetsBand() {
  return (
    <Band
      id="tearsheets"
      title="Tearsheets"
      takeaway="Live prices, then one strategy at a time."
    >
      <div className="min-w-0 border border-hair">
        <MarketBarShell />
        <StrategyRailLive />
      </div>
    </Band>
  );
}
