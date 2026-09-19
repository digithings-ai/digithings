import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { LivePortfolioPanel } from "./DashboardPortfolioPanel";
import type { LivePosition } from "@/lib/live";

const POSITIONS: LivePosition[] = [
  {
    ticker: "VGK",
    name: "Vanguard FTSE Europe",
    category: "etf",
    sectorBucket: "international",
    weightPct: 24.8,
    entryPrice: 90.99,
    entryDate: "2026-08-20",
    currentPrice: 90.9,
    dayChangePct: 0.2,
    unrealizedPnlPct: -0.1,
    sinceEntryReturnPct: -0.1,
    metricsAsOf: "2026-01-02",
    livePrice: 91.1,
    isLive: true,
  },
  {
    ticker: "CASH",
    name: null,
    category: null,
    sectorBucket: null,
    weightPct: 75.2,
    entryPrice: null,
    entryDate: null,
    currentPrice: null,
    dayChangePct: null,
    unrealizedPnlPct: null,
    sinceEntryReturnPct: null,
    metricsAsOf: null,
    livePrice: null,
    isLive: false,
  },
];

vi.mock("@/lib/live", () => ({
  useLivePortfolio: () => ({
    configured: true,
    loading: false,
    error: null,
    navContractError: null,
    positions: POSITIONS,
    nav: [],
    latestNav: null,
    liveTotalValue: null,
    liveVsMarkPct: 0.42,
    metricsAsOf: "2026-01-02",
    kpis: null,
    isResearchPortfolio: true,
  }),
}));

describe("live positions blotter on the kit Table (wave 2 T3)", () => {
  const html = renderToStaticMarkup(<LivePortfolioPanel />);

  it("renders the kit Table shell", () => {
    expect(html).toContain('data-slot="table"');
    expect(html).toContain('data-slot="table-container"');
    expect(html).toContain("min-w-[560px]");
    expect(html).not.toContain("border-collapse font-mono");
  });

  it("keeps all six columns and the book rows", () => {
    for (const h of ["ticker", "sleeve", "weight", "price", "day", "since entry"]) {
      expect(html).toContain(`>${h}<`);
    }
    expect(html).toContain("VGK");
    expect(html).toContain("CASH");
    expect(html).toContain("international");
    expect(html).toContain("24.8%");
    expect(html).toContain("75.2%");
  });

  it("preserves the live-flash cells and their tone/markup", () => {
    expect(html).toContain("dq-tick");
    expect(html.match(/dq-tick/g)!.length).toBeGreaterThanOrEqual(3);
    expect(html).toContain("text-up");
    expect(html).toContain("text-ink-soft");
    expect(html).toContain("91.10");
    expect(html).toContain("+0.20%");
    expect(html).toContain("bg-accent");
  });

  it("keeps the per-leg live badge", () => {
    expect(html).toContain('aria-label="VGK price is live"');
  });
});
