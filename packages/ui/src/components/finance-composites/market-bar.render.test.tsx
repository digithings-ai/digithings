import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MarketBar, percentPulseGeneration, type MarketBarCell } from "./MarketBar";

const CELLS: MarketBarCell[] = [
  { symbol: "BTC", value: "63,410", changePct: 0.4 },
  { symbol: "ETH", value: "3,088", changePct: -0.62, flashKey: 1 },
  { symbol: "SPY", value: "548.21", changePct: -0.2, asOf: "as of 09-29", source: "daily close" },
  { symbol: "GOLD", value: null },
];

describe("percentPulseGeneration", () => {
  it("pulses only after a finite percent actually changes", () => {
    expect(percentPulseGeneration(undefined, 1.2, 0)).toEqual({ previous: 1.2, generation: 0 });
    expect(percentPulseGeneration(undefined, null, 0)).toEqual({ previous: null, generation: 0 });
    expect(percentPulseGeneration(1.2, 1.2, 0)).toEqual({ previous: 1.2, generation: 0 });
    expect(percentPulseGeneration(1.2, 1.3, 0)).toEqual({ previous: 1.3, generation: 1 });
    expect(percentPulseGeneration(1.2, null, 1)).toEqual({ previous: null, generation: 1 });
    expect(percentPulseGeneration(null, 0.4, 1)).toEqual({ previous: 0.4, generation: 2 });
  });
});

describe("MarketBar", () => {
  it("shows a square mark only while the feed is ticking, without the word", () => {
    const live = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(live).toContain("mb-live-mark");
    expect(live).not.toContain("ts-live-badge");
    expect(live).not.toContain("ts-live-dot");
    expect(live.replace(/<[^>]+>/g, " ").toLowerCase()).not.toContain("live");
    for (const status of ["connecting", "stale", "offline"] as const) {
      const html = renderToStaticMarkup(<MarketBar cells={CELLS} status={status} />);
      expect(html, status).not.toContain("mb-live-mark");
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
    expect(html).toContain("GOLD no value percent unavailable");
    expect(html).toContain('data-mb="pct">—');
    expect(html).toContain('data-mb="pct">0.40%');
    const btc = html.split(">BTC<").length - 1;
    expect(btc).toBe(2);
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

  it("never pulses a percent on first paint", () => {
    const html = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(html).not.toContain("mb-pct-pulse");
    expect(html).not.toContain("mb-flash");
  });

  it("keeps the repeated list flush and the live mark square", () => {
    const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../styles/marquee.css"), "utf8");
    const rule = css.match(/\.mb-tape\.mq-row \.mq-group\s*\{[^}]*\}/)?.[0] ?? "";
    expect(rule).toContain("gap: 0");
    expect(rule).toContain("padding-inline-end: 0");
    expect(rule).toContain("flex: 0 0 auto");
    const mark = css.match(/\.mb-live-mark\s*\{[^}]*\}/)?.[0] ?? "";
    expect(mark).toContain("border-radius: 0");
    expect(mark).not.toContain("50%");
    expect(mark).toContain("var(--up)");
  });

  it("uses no raw colour", () => {
    const html = renderToStaticMarkup(<MarketBar cells={CELLS} status="live" />);
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});
