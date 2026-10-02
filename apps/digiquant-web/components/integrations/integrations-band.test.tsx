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
    expect(html).toContain("NautilusTrader");
    expect(html).toContain("local gateway below");
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
    expect(html).toContain("Local wire checks after hydration");
  });

  it("keeps the platform row, the quiet secondary marks, and the showcase line", () => {
    expect(html).toContain("agentic workflows");
    expect(html).toContain("digichat is where a strategy idea starts");
    expect(html).toContain("also connected");
    expect(html).toContain("Coinbase");
    expect(html).toContain("Alpaca");
    expect(html).toContain("Interactive Brokers");
    expect(html).toContain("places no orders");
    expect(html).toContain("live LuxAlgo Vela");
  });

  it("keeps driver cards from forcing a single nowrap line", () => {
    const card = html.slice(html.indexOf('href="https://github.com/gloom-sh/gloomberb"'));
    const className = card.match(/class="([^"]*)"/)?.[1] ?? "";
    expect(className).toContain("whitespace-normal");
    expect(className).toContain("min-w-0");
    expect(className).not.toContain("whitespace-nowrap");
  });
});
