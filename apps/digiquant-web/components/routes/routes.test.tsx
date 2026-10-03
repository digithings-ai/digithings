import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import ChangelogPage from "@/app/changelog/page";
import ContactPage from "@/app/contact/page";
import StrategiesPage from "@/app/strategies/page";
import TearsheetPage from "@/app/strategies/[id]/page";

describe("linked routes", () => {
  it("lists real tagged releases and does not say placeholder", () => {
    const html = renderToStaticMarkup(<ChangelogPage />);
    expect(html).toContain("digichat 2.4.0");
    expect(html).toContain("digiskills 0.2.1");
    expect(html).toContain("no product tag");
    expect(html).not.toContain(">placeholder<");
  });

  it("keeps managed contact at Coming soon", () => {
    const html = renderToStaticMarkup(<ContactPage />);
    expect(html).toContain("Coming soon");
    expect(html).toContain("Write to us");
    expect(html).toContain("Free");
    expect(html).not.toContain(">placeholder<");
  });

  it("shows one tear sheet and leaves unpublished figures as em dashes", async () => {
    const index = renderToStaticMarkup(<StrategiesPage />);
    expect(index).toContain("BTC L/S");
    expect(index).toContain("ETH L/S");
    expect(index).toContain("SOL L/S");
    expect(index).toContain("BTC-SDCA");
    expect(index).toContain("—");
    expect(index).not.toContain("The official API has not published strategy statistics");
    expect(index).not.toContain("backtest · illustrative, in-sample");
    expect(index).not.toContain("Backtest only");
    expect(index).not.toContain(">placeholder<");

    const detail = renderToStaticMarkup(await TearsheetPage({ params: Promise.resolve({ id: "btc_slapper" }) }));
    expect(detail).toContain("CAGR");
    expect(detail).toContain("—");
    expect(detail).not.toContain("The official API has not published strategy statistics");
    expect(detail).not.toContain("Backtest only");
    expect(detail).not.toContain(">placeholder<");
  });
});
