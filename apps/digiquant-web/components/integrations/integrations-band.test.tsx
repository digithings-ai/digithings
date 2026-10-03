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
    expect(html).toContain("The live chart is the hero");
  });

  it("does not mount the LuxAlgo library demo", () => {
    expect(html).not.toContain("LuxAlgo, as a demo");
    expect(html).not.toContain("Search LuxAlgo Library");
    expect(html).not.toContain("Continue in LuxAlgo");
    expect(html).not.toContain("Research metadata only");
    expect(html).not.toContain("Local wire checks after hydration");
    expect(html).not.toContain("luxalgo-library-query");
    expect(html).not.toContain("The hero chart is live LuxAlgo Vela");
  });

  it("uses the digithings hero wordmark and the modules this stack runs", () => {
    expect(html).toContain("pixel-word-hero");
    expect(html).toContain('aria-label="digithings"');
    expect(html).toContain("The platform that drives the agentic side of digiquant.");
    expect(html).toContain("digigraph");
    expect(html).toContain("Orchestrates the research and portfolio runs.");
    expect(html).toContain("digichat");
    expect(html).toContain("The chat where a strategy idea starts.");
    expect(html).toContain("digillm");
    expect(html).toContain("digikey");
    expect(html).toContain("digibase");
    expect(html).toContain("digifetch");
    expect(html).not.toContain("favicon-dg.svg");
    expect(html).not.toMatch(/12x|fx hub/i);
  });

  it("scrolls the packages this tree actually calls, in two directions", () => {
    expect(html).toContain("Coinbase · public price feed");
    expect(html).toContain("Alpaca · broker adapter");
    expect(html).toContain("Interactive Brokers · broker adapter");
    expect(html).toContain("Kraken · account snapshots");
    expect(html).toContain("Tradier · account snapshots");
    expect(html).toContain("Yahoo Finance · quote history");
    expect(html).toContain("FRED · macro series");
    expect(html).toContain("Supabase · stored prices");
    expect(html).toContain("Binance · chart prices");
    expect(html).toContain("mq-track--left");
    expect(html).toContain("mq-track--right");
    expect(html).not.toContain("also connected");
  });

  it("drops the showcase tag, the collapse control, and the disclaimer", () => {
    expect(html).not.toContain("showcase only");
    expect(html).not.toContain(">Collapse<");
    expect(html).not.toContain(">Expand<");
    expect(html).not.toContain("places no orders");
    expect(html).not.toContain("no live trading");
    expect(html).not.toContain("implies no affiliation");
  });

  it("keeps driver cards from forcing a single nowrap line", () => {
    const card = html.slice(html.indexOf('href="https://github.com/gloom-sh/gloomberb"'));
    const className = card.match(/class="([^"]*)"/)?.[1] ?? "";
    expect(className).toContain("whitespace-normal");
    expect(className).toContain("min-w-0");
    expect(className).not.toContain("whitespace-nowrap");
  });
});
