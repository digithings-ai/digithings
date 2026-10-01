import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { LocalLuxalgoWorkflow } from "./local-luxalgo-workflow";

describe("LocalLuxalgoWorkflow", () => {
  const html = renderToStaticMarkup(<LocalLuxalgoWorkflow />);

  it("keeps LuxAlgo as the chart and journal handoff", () => {
    expect(html).toContain("chart + journal");
    expect(html).toContain("Continue in LuxAlgo");
    expect(html).toContain("renders no competing chart");
    expect(html).toContain('href="https://www.luxalgo.com/"');
  });

  it("frames the search as a demo, not the product", () => {
    expect(html).toContain("as a demo");
    expect(html).toContain("not a search tool");
    expect(html).toContain("The product is the dashboard");
  });

  it("renders the local-only Library search control and honest initial state", () => {
    expect(html).toContain("Search LuxAlgo Library");
    expect(html).toContain("Local wire checks after hydration");
    expect(html).toContain("Research metadata only");
  });

  it("does not render a chart surface or live-trading claim", () => {
    expect(html).not.toContain("<canvas");
    expect(html).not.toContain("live trading");
  });
});
