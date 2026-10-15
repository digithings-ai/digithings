import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { IntegrationsBand } from "@/app/_bands/integrations";
import { rowMark, type RowProviderId } from "@/components/integrations/marks";

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
    expect(html).not.toContain("M-9 -5.5 -2 0 -9 5.5");
  });

  it("drops the big digiquant hero and the emblem icons; every module tile shows its own small banner", () => {
    expect(html).not.toContain('aria-label="digiquant"');
    expect(html).not.toContain("M0 -6 -9 8");
    const modules = [
      "digigraph", "digichat", "digillm", "digikey", "digibase", "digifetch",
      "digisearch", "digitrace", "digivault", "digiclaw", "digivoice", "digidev", "digibook",
    ];
    for (const name of modules) {
      expect(html).toMatch(new RegExp(`<canvas[^>]*aria-label="${name}"`));
      expect(html).not.toContain(`>${name}</span>`);
    }
    expect(html.match(/<canvas/g) ?? []).toHaveLength(modules.length);
    expect(html).toContain('aria-label="digiquant calls"');
    expect(html).toContain('aria-label="the rest of digithings"');
  });

  it("scrolls the packages this tree actually calls, in two directions", () => {
    expect(html).toContain("Coinbase · public price feed");
    expect(html).toContain("Alpaca · broker adapter");
    expect(html).toContain("Interactive Brokers · broker adapter");
    expect(html).toContain("Kraken · account snapshots");
    expect(html).toContain("Tradier · account snapshots");
    expect(html).toContain("Yahoo Finance · quote history");
    expect(html).not.toContain("FRED");
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

/**
 * DIG-2861 — a logo per provider in the two sliding rows.
 *
 * The acceptance asks for no text-only entries left. That is NOT met: Simple Icons
 * (the CC0 source of official monochrome brand paths this repo already uses) carries
 * no path for Alpaca, Interactive Brokers, Kraken, Tradier, Yahoo Finance or FRED.
 * These tests pin the two things that must be true either way — a provider with an
 * official mark shows it, and a provider without one is left plain rather than given
 * a lookalike — so the gap stays visible and cannot be closed with a fake.
 */
describe("connected-package row marks", () => {
  const html = renderToStaticMarkup(<IntegrationsBand />);
  const rowsHtml = html.slice(html.indexOf('aria-label="Connected packages"'));

  /** Simple Icons 15.22.0 — verified by importing the pinned package, not by
   *  reading a registry file. */
  const WITH_OFFICIAL_MARK: RowProviderId[] = ["coinbase", "supabase", "binance"];
  const WITHOUT_OFFICIAL_MARK: RowProviderId[] = ["alpaca", "ibkr", "kraken", "tradier", "yahoo", "fred"];

  it("knows which providers have an official monochrome path", () => {
    for (const id of WITH_OFFICIAL_MARK) expect(rowMark(id)).not.toBeNull();
    for (const id of WITHOUT_OFFICIAL_MARK) expect(rowMark(id)).toBeNull();
  });

  it("draws every official mark in the rows, in the row's own colour", () => {
    // Marquee renders its content twice (two .mq-group spans) so the -50% loop is
    // seamless, so each mark is expected twice.
    const marks = rowsHtml.match(/<svg[^>]*viewBox="0 0 24 24"/g) ?? [];
    expect(marks).toHaveLength(WITH_OFFICIAL_MARK.length * 2);
    // monochrome by construction: the path paints with currentColor, never a brand hex
    expect(rowsHtml).not.toMatch(/<path[^>]*fill="#/);
  });

  it("leaves a provider with no official mark plain, with no lookalike", () => {
    // A scraped favicon, a recoloured app icon or a hand-drawn monogram would be
    // something other than the vendor's own mark.
    expect(rowsHtml).not.toContain("<img");
    expect(rowsHtml).not.toMatch(/inline-grid[^"]*place-items-center/);
    // every label still reads, marked or not
    for (const label of [
      "Alpaca · broker adapter",
      "Interactive Brokers · broker adapter",
      "Kraken · account snapshots",
      "Tradier · account snapshots",
      "Yahoo Finance · quote history",
    ]) {
      expect(rowsHtml).toContain(label);
    }
  });
});
