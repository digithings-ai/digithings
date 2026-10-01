import { DashboardBand } from "./_bands/dashboard";
import { PipelineBand } from "./_bands/pipeline";
import { ProductsBand } from "./_bands/products";
import { StartBand } from "./_bands/start";
import { StrategyBand } from "./_bands/strategy";
import { TearsheetsBand } from "./_bands/tearsheets";
import { TopBand } from "./_bands/top";

// Phase 0a shell: bands render in registry order. Each band is its own file so
// later passes touch only their band. Band order lives in _bands/registry.ts.
export default function Home() {
  return (
    <main id="main" className="[--page-step:clamp(2rem,4.5vw,3.5rem)]">
      <TopBand />
      <ProductsBand />
      <PipelineBand />
      <TearsheetsBand />
      <StrategyBand />
      <DashboardBand />
      <StartBand />
    </main>
  );
}
