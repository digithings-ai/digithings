import { ChatBand } from "./_bands/chat";
import { DashboardBand } from "./_bands/dashboard";
import { IntegrationsBand } from "./_bands/integrations";
import { McpBand } from "./_bands/mcp";
import { PipelineBand } from "./_bands/pipeline";
import { StartBand } from "./_bands/start";
import { TearsheetsBand } from "./_bands/tearsheets";
import { TopBand } from "./_bands/top";

// Bands render in the showcase order from _bands/registry.ts. Each band is its
// own file so a pass touches only its band.
export default function Home() {
  return (
    <main id="main" className="[--page-step:clamp(2rem,4.5vw,3.5rem)]">
      <TopBand />
      <DashboardBand />
      <PipelineBand />
      <ChatBand />
      <McpBand />
      <TearsheetsBand />
      <IntegrationsBand />
      <StartBand />
    </main>
  );
}
