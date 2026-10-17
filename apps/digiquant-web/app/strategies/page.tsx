import type { Metadata } from "next";
import { DocumentFrame, PageTitle } from "@digithings/ui";
import { StrategyRailLive } from "@/components/tearsheet/rail/strategy-rail-live";

export const metadata: Metadata = {
  title: "Strategies — digiquant",
  description: "Backtest tearsheets for published digiquant strategies. Unpublished statistics stay an em dash.",
};

export default function StrategiesPage() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <div className="px-[var(--page-pad)] py-[var(--page-step)]">
          <PageTitle title="Strategies">
            Backtest tearsheets for the strategies this site has a route for. A statistic appears only after the live store publishes it.
          </PageTitle>
          <div className="mt-8">
            <StrategyRailLive />
          </div>
        </div>
      </DocumentFrame>
    </main>
  );
}
