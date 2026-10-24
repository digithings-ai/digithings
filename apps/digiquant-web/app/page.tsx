import type { Metadata } from "next";
import { ChatBand } from "./_bands/chat";
import { DashboardBand } from "./_bands/dashboard";
import { IntegrationsBand } from "./_bands/integrations";
import { McpBand } from "./_bands/mcp";
import { PipelineBand } from "./_bands/pipeline";
import { StartBand } from "./_bands/start";
import { TearsheetsBand } from "./_bands/tearsheets";
import { TopBand } from "./_bands/top";

// The home is the only route that is the product page, so its canonical and
// card metadata live here rather than in the root layout (which every route
// inherits). `trailingSlash: true` in next.config resolves "/" to the root URL
// with the trailing slash kept.
const TITLE = "digiquant — a quant research desk in a glass box you own";
const DESCRIPTION =
  "See the digiquant dashboard at work: the house book, how a strategy is built, and the "
  + "tooling underneath. Open-source, self-hosted, with a decision log per run.";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: [{ url: "/og.png", width: 1200, height: 630, alt: TITLE }],
  },
};

// Bands render in the showcase order from _bands/registry.ts. Each band is its
// own file so a pass touches only its band.
export default function Home() {
  return (
    // tabIndex -1 makes the nav's skip link land focus here, as on every other
    // route in this app.
    <main id="main" tabIndex={-1} className="[--page-step:clamp(2rem,4.5vw,3.5rem)]">
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
