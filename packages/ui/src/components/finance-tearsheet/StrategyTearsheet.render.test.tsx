import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StrategyTearsheet } from "./StrategyTearsheet";
import { buildStrategyTearsheet } from "./strategy-sheet-model";

describe("StrategyTearsheet", () => {
  it("shows em dashes and no chart when the payload is unpublished", () => {
    const html = renderToStaticMarkup(
      <StrategyTearsheet model={buildStrategyTearsheet(null, { title: "BTC L/S", symbol: "BTC-USD" })} />,
    );
    expect(html).toContain("BTC L/S");
    expect(html).toContain("Current position");
    expect(html).toContain("Entries and exits");
    expect(html).toContain("—");
    expect(html).not.toContain("ts-chart");
    expect(html).not.toContain("Backtest only");
    expect(html).not.toContain("official API");
  });

  it("draws a chart only after two real equity points", () => {
    const one = renderToStaticMarkup(
      <StrategyTearsheet
        model={buildStrategyTearsheet(
          { equity_curve: [{ t: "2024-01-01", v: 1 }] },
          { title: "ETH L/S", symbol: "ETH-USD" },
        )}
      />,
    );
    expect(one).not.toContain("ts-chart");
    const two = renderToStaticMarkup(
      <StrategyTearsheet
        model={buildStrategyTearsheet(
          {
            equity_curve: [
              { t: "2024-01-01", v: 1 },
              { t: "2024-02-01", v: 2 },
            ],
          },
          { title: "ETH L/S", symbol: "ETH-USD" },
        )}
      />,
    );
    expect(two).toContain("ts-chart");
    expect(two).toContain('aria-label="ETH L/S equity"');
  });
});
