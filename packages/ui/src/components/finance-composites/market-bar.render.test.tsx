import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MarketBar, type MarketBarCell } from "./MarketBar";

const CELLS: MarketBarCell[] = [
  { symbol: "BTC", value: "63,410", changePct: 0.4 },
  { symbol: "ETH", value: "3,088", changePct: -0.62, flashKey: 1 },
  { symbol: "SPY", value: "548.21", changePct: -0.2, asOf: "as of 09-29", source: "daily close" },
  { symbol: "GOLD", value: null },
];

describe("MarketBar", () => {
  it("shows the live badge only for status live", () => {
    expect(renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />)).toContain("ts-live-badge");
    for (const status of ["connecting", "stale", "offline"] as const) {
      const html = renderToStaticMarkup(<MarketBar cells={CELLS} status={status} />);
      expect(html, status).not.toContain("ts-live-badge");
      expect(html, status).toContain(`[${status}]`);
    }
  });

  it("renders connecting… with no prices and no controls when empty", () => {
    const html = renderToStaticMarkup(<MarketBar cells={[]} status="connecting" />);
    expect(html).toContain("connecting…");
    expect(html).not.toContain("[pause]");
    expect(html).not.toContain("mq-row");
    expect(renderToStaticMarkup(<MarketBar cells={[]} status="offline" />)).toContain("offline");
  });

  it("hides the marquee from AT and carries a plain-text summary, aria-live off", () => {
    const html = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(html).toContain('aria-live="off"');
    expect(html).toMatch(/aria-hidden="true"[^>]*class="min-w-0 flex-1"/);
    expect(html).toContain("sr-only");
    expect(html).toContain("BTC 63,410 up 0.40%");
    expect(html).toContain("ETH 3,088 down 0.62%");
    expect(html).toContain("SPY 548.21 down 0.20% as of 09-29 source daily close");
    expect(html).toContain("GOLD no value");
  });

  it("offers a pause control and pauses the marquee via data-paused", () => {
    const running = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(running).toContain("[pause]");
    expect(running).toContain('aria-pressed="false"');
    expect(running).not.toContain('data-paused="true"');
    const paused = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" defaultPaused />);
    expect(paused).toContain("[play]");
    expect(paused).toContain('data-paused="true"');
  });

  it("wears money colours only on the signed change; null values show a dash", () => {
    const html = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(html).toContain("is-pos");
    expect(html).toContain("is-neg");
    expect(html).not.toContain("text-up");
    expect(html).not.toContain("text-down");
    expect(html).toContain(">—<");
  });

  it("never flashes on first paint (flashKey only flashes on change)", () => {
    const html = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(html).not.toContain("mb-flash");
  });

  it("uses no raw colour", () => {
    const html = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
