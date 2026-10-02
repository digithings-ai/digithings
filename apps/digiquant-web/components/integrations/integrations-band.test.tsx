import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { IntegrationsBand } from "@/app/_bands/integrations";

describe("IntegrationsBand", () => {
  const html = renderToStaticMarkup(<IntegrationsBand />);

  it("names the drivers and links them out", () => {
    expect(html).toContain("Gloomberg");
    expect(html).toContain('href="https://github.com/gloom-sh/gloomberb"');
    expect(html).toContain('href="https://www.luxalgo.com/"');
    expect(html).toContain('href="https://nautilustrader.io/"');
    expect(html).toContain('href="https://digithings.ai"');
  });

  it("does not draw a fake preview in place of a feed", () => {
    expect(html).not.toContain("Terminal-style quote strip");
    expect(html).not.toContain("Live Vela candlestick preview");
    expect(html).not.toContain("Backtest run timeline");
  });

  it("mounts the local LuxAlgo lookup with its offline-honest copy", () => {
    expect(html).toContain("LuxAlgo, as a demo");
    expect(html).toContain("Search LuxAlgo Library");
    expect(html).toContain("places no orders");
  });
});
