import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TearsheetsBand } from "@/app/_bands/tearsheets";
import { StrategyRailLive } from "./strategy-rail-live";

describe("landing tearsheets", () => {
  it("drops the non-client unpublished copy", () => {
    const html = renderToStaticMarkup(<TearsheetsBand />);
    expect(html.toLowerCase()).not.toContain("unpublished");
    expect(html).not.toContain("as of");
  });

  it("preloads every strategy inside one box under a strategy banner", () => {
    const html = renderToStaticMarkup(<StrategyRailLive compact />);
    expect(html).toContain(">Strategy<");
    for (const label of ["BTC L/S", "ETH L/S", "SOL L/S", "BTC-SDCA"]) {
      expect(html).toContain(label);
    }
    expect(html.match(/ts-compact/g) ?? []).toHaveLength(4);
    expect(html.match(/hidden=""/g) ?? []).toHaveLength(3);
  });
});
