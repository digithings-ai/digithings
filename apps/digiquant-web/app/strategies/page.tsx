import type { Metadata } from "next";
import { DocumentFrame, PageTitle } from "@digithings/ui";

export const metadata: Metadata = {
  title: "Strategies — digiquant",
  description: "Backtest tearsheets for published digiquant strategies.",
};

export default function StrategiesPage() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <PageTitle title="Strategies">placeholder</PageTitle>
      </DocumentFrame>
    </main>
  );
}
