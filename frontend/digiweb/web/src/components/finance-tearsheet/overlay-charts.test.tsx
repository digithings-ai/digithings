import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MultiTimeSeries, RiskBandStrip, AllocationStepChart } from "./charts";
import { dcaRateCopy, riskBandLabel } from "./risk-bands";

const DATES = ["2024-01-01", "2024-01-02", "2024-01-03"];

describe("riskBandLabel", () => {
  it("maps the published SDCA bands, treating 95–100 as Bubble", () => {
    expect(riskBandLabel(0)).toBe("Fire sale");
    expect(riskBandLabel(9.9)).toBe("Fire sale");
    expect(riskBandLabel(10)).toBe("Accumulate");
    expect(riskBandLabel(24.9)).toBe("Accumulate");
    expect(riskBandLabel(25)).toBe("Value");
    expect(riskBandLabel(50)).toBe("Above mid");
    expect(riskBandLabel(75)).toBe("Hot");
    expect(riskBandLabel(95)).toBe("Bubble");
    expect(riskBandLabel(100)).toBe("Bubble");
    expect(riskBandLabel(null)).toBeNull();
  });
});

describe("dcaRateCopy", () => {
  it("describes buy / sell / hold without implying a 100× unit error", () => {
    expect(dcaRateCopy(4)).toBe("buying 4.0% of remaining cash today");
    expect(dcaRateCopy(-2.5)).toBe("selling 2.5% of remaining holdings today");
    expect(dcaRateCopy(0)).toBe("holding, no trade today");
    expect(dcaRateCopy(null)).toBeNull();
  });
});

describe("MultiTimeSeries", () => {
  it("renders each overlay series as a stroked path with data-series", () => {
    const html = renderToStaticMarkup(
      createElement(MultiTimeSeries, {
        series: [
          {
            id: "spot",
            label: "Spot",
            points: DATES.map((t, i) => ({ t, v: 100 + i })),
            tone: "accent",
            fill: true,
          },
          {
            id: "low",
            label: "Low rail",
            points: DATES.map((t, i) => ({ t, v: 80 + i })),
            tone: "mute",
            dashed: true,
          },
          {
            id: "high",
            label: "High rail",
            points: DATES.map((t, i) => ({ t, v: 120 + i })),
            tone: "mute",
            dashed: true,
          },
        ],
        ariaLabel: "Valuation rails",
      }),
    );
    expect(html).toContain('data-series="spot"');
    expect(html).toContain('data-series="low"');
    expect(html).toContain('data-series="high"');
    expect(html).toContain('data-chart-layer="overlay-line"');
    expect(html).toContain("ts-line-dashed");
    expect(html).toContain("ts-tone-mute");
    expect(html.match(/<svg/g)).toHaveLength(1);
  });

  it("degrades to empty when every series has no points", () => {
    const html = renderToStaticMarkup(
      createElement(MultiTimeSeries, {
        series: [{ id: "x", label: "X", points: [] }],
        ariaLabel: "empty overlay",
      }),
    );
    expect(html).toContain("no data");
  });
});

describe("RiskBandStrip", () => {
  it("paints the six labelled bands and a risk line", () => {
    const html = renderToStaticMarkup(
      createElement(RiskBandStrip, {
        points: [
          { t: "2024-01-01", v: 8 },
          { t: "2024-01-02", v: 40 },
          { t: "2024-01-03", v: 96 },
        ],
        ariaLabel: "Composite risk 0 to 100",
      }),
    );
    expect(html).toContain('data-chart-layer="risk-bands"');
    expect(html).toContain('data-chart-layer="risk-line"');
    expect(html).toContain('data-band="fire"');
    expect(html).toContain('data-band="acc"');
    expect(html).toContain('data-band="value"');
    expect(html).toContain('data-band="mid"');
    expect(html).toContain('data-band="hot"');
    expect(html).toContain('data-band="bubble"');
    expect(html.match(/<svg/g)).toHaveLength(1);
  });

  it("draws accumulate/distribute knees and a faint price overlay", () => {
    const html = renderToStaticMarkup(
      createElement(RiskBandStrip, {
        points: [
          { t: "2024-01-01", v: 20 },
          { t: "2024-01-02", v: 70 },
        ],
        thresholds: [
          { id: "buy", value: 25, label: "accumulate (oversold) 25" },
          { id: "sell", value: 70, label: "distribute (overbought) 70" },
        ],
        priceOverlay: [
          { t: "2024-01-01", v: 40000 },
          { t: "2024-01-02", v: 42000 },
        ],
        ariaLabel: "Index with knees",
      }),
    );
    expect(html).toContain('data-chart-layer="risk-threshold"');
    expect(html).toContain('data-threshold="buy"');
    expect(html).toContain('data-threshold="sell"');
    expect(html).toContain("accumulate (oversold) 25");
    expect(html).toContain('data-chart-layer="price-overlay"');
  });
});

describe("AllocationStepChart", () => {
  it("renders allocated step and sized buy/sell fill dots, without a cash line", () => {
    const html = renderToStaticMarkup(
      createElement(AllocationStepChart, {
        allocated: [
          { t: "2025-01-19", v: 90 },
          { t: "2025-01-20", v: 70 },
        ],
        markers: [
          { t: "2025-01-19", side: "buy", book_frac: 0.05 },
          { t: "2025-01-20", side: "sell", book_frac: 0.12 },
        ],
        priceOverlay: [
          { t: "2025-01-19", v: 90000 },
          { t: "2025-01-20", v: 102000 },
        ],
        ariaLabel: "Allocation step chart",
      }),
    );
    expect(html).toContain('data-chart-layer="alloc-step"');
    expect(html).not.toContain('data-chart-layer="cash-step"');
    expect(html).toContain('data-chart-layer="fill-markers"');
    expect(html).toContain('data-side="buy"');
    expect(html).toContain('data-side="sell"');
    expect(html).toContain('data-chart-layer="price-overlay"');
  });
});
