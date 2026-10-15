import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import ChangelogPage from "@/app/changelog/page";
import ContactPage from "@/app/contact/page";
import StrategiesPage from "@/app/strategies/page";
import TearsheetPage from "@/app/strategies/[id]/page";

describe("linked routes", () => {
  it("lists real tagged releases and does not say placeholder", () => {
    const html = renderToStaticMarkup(<ChangelogPage />);
    expect(html).toContain("digichat 2.3.2");
    expect(html).not.toContain("digichat 2.4.0");
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

  it("keeps one h1 per page: the embedded sheet demotes its title to h2", () => {
    // The landing and /strategies pages already carry the page h1, so the
    // tearsheet rail must not mint a second one (DIG-3446). The sheet title
    // only renders after the client data fetch, which static markup cannot
    // reach — so this pins the branch in source (with a live-read control),
    // and the re-run audit proves the behaviour (one h1 + h2.ts-h1).
    const view = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "..", "tearsheet", "tearsheet-view.tsx"),
      "utf8",
    );
    // Control: the read is live — the shared title class occurs in both branches.
    expect(view.length).toBeGreaterThan(10000);
    expect(view.split("ts-h1 ts-h1-with-logo").length - 1).toBe(2);
    // Exactly one h1 (standalone page) and one h2 (embedded rail).
    expect(view.split('<h1 className="ts-h1').length - 1).toBe(1);
    expect(view.split('<h2 className="ts-h1').length - 1).toBe(1);
    // The h2 sits in the embedded branch.
    const embeddedAt = view.indexOf("embedded ? (");
    expect(embeddedAt).toBeGreaterThan(-1);
    expect(view.slice(embeddedAt, embeddedAt + 800)).toContain('<h2 className="ts-h1');
  });
});
