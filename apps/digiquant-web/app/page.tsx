import { DashboardBand } from "./_bands/dashboard";
import { PipelineBand } from "./_bands/pipeline";
import { ProductsBand } from "./_bands/products";
import { StartBand } from "./_bands/start";
import { StrategyBand } from "./_bands/strategy";
import { TearsheetsBand } from "./_bands/tearsheets";
import { TopBand } from "./_bands/top";

// Bands render in the showcase order from _bands/registry.ts. Each band is its
// own file so a pass touches only its band.
export default function Home() {
  return (
    <main id="main" className="[--page-step:clamp(2rem,4.5vw,3.5rem)]">
      <TopBand />
      <DashboardBand />
      <StrategyBand />
      <PipelineBand />
      <TearsheetsBand />
      <ProductsBand />
      <StartBand />
    </main>
  );
}
