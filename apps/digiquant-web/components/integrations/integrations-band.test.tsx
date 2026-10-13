import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { IntegrationsBand, PACKAGES_A, PACKAGES_B } from "@/app/_bands/integrations";
import { rowMark, type RowProviderId } from "@/components/integrations/marks";

describe("IntegrationsBand", () => {
  const html = renderToStaticMarkup(<IntegrationsBand />);
  /** Everything from the rows down. The driver cards above them carry their own
   *  marks, so a count taken over the whole band would not be about the rows. */
  const rowsHtml = html.slice(html.indexOf('aria-label="Connected packages"'));

  it("names the drivers and links them out", () => {
    expect(html).toContain("Gloomberg");
    expect(html).toContain('href="https://github.com/gloom-sh/gloomberb"');
    expect(html).toContain('href="https://www.luxalgo.com/"');
    expect(html).toContain('href="https://nautilustrader.io/"');
    expect(html).toContain('href="https://digithings.ai"');
    expect(html).toContain("NautilusTrader");
    expect(html).toContain("market data");
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

  it("names digithings and the modules this stack calls, without hero banners", () => {
    expect(html).toContain(">digithings<");
    expect(html).toContain("favicon-dg.svg");
    expect(html).not.toContain("pixel-word-hero");
    expect(html).not.toContain("<canvas");
    for (const name of ["digigraph", "digichat", "digillm", "digikey", "digibase", "digifetch"]) {
      expect(html).toContain(`>${name}<`);
    }
    for (const name of ["digisearch", "digitrace", "digivault", "digiclaw", "digivoice", "digidev", "digibook"]) {
      expect(html).not.toContain(`>${name}<`);
    }
    expect(html).toContain('aria-label="digiquant calls"');
    expect(html).not.toContain('aria-label="the rest of digithings"');
    expect(html).not.toMatch(/12x|fx hub/i);
  });

  it("scrolls every other provider once, in two directions", () => {
    const ids = [...PACKAGES_A, ...PACKAGES_B].map((entry) => entry.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.filter((id) => id === "supabase")).toHaveLength(1);
    expect(html).toContain("Coinbase");
    expect(html).toContain("Alpaca");
    expect(html).toContain("Interactive Brokers");
    expect(html).toContain("Kraken");
    expect(html).toContain("Tradier");
    expect(html).toContain("Yahoo Finance");
    expect(html).toContain("Cloudflare");
    expect(html).toContain("Stripe");
    expect(html).toContain("Optuna");
    expect(html).not.toContain("FRED");
    expect(html).toContain("Supabase");
    expect(html).toContain("Binance");
    expect(html).toContain("mq-fill");
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

/** A logo on every connected provider. Official paths stay monochrome; the rest are initials. */
describe("connected-package row marks", () => {
  const html = renderToStaticMarkup(<IntegrationsBand />);
  const rowsHtml = html.slice(html.indexOf('aria-label="Connected packages"'));

  const WITH_OFFICIAL_MARK: RowProviderId[] = ["coinbase", "supabase", "binance", "cloudflare", "stripe", "optuna"];
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

  it("gives a provider with no official path an initials mark", () => {
    expect(rowsHtml).not.toContain("<img");
    const monograms = rowsHtml.match(/inline-grid[^"]*place-items-center/g) ?? [];
    const shown = [...PACKAGES_A, ...PACKAGES_B].filter((entry) => WITHOUT_OFFICIAL_MARK.includes(entry.id));
    expect(monograms).toHaveLength(shown.length * 2);
    for (const label of ["Alpaca", "Interactive Brokers", "Kraken", "Tradier", "Yahoo Finance"]) {
      expect(rowsHtml).toContain(label);
    }
  });
});
