import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DIGIQUANT_CHART, readDigiquantChartScale } from "./chart-scale";

const tokens = readFileSync(new URL("../../../../design/tokens.css", import.meta.url), "utf8");

describe("digiquant chart scale", () => {
  it("aliases the canon up and down pair and keeps grid and axis neutral", () => {
    const shared = tokens.slice(tokens.indexOf(":root[data-theme] {"));
    expect(shared).toContain("--chart-candle-up: var(--up);");
    expect(shared).toContain("--chart-candle-down: var(--down);");
    expect(shared).toContain("--chart-volume-up: var(--up);");
    expect(shared).toContain("--chart-volume-down: var(--down);");
    expect(shared).toContain("--chart-sma: var(--up);");
    expect(shared).toContain("--chart-ema: var(--down);");
    expect(shared).toContain("--chart-vwap: var(--up);");
    expect(shared).toContain("--chart-bollinger: var(--down);");
    expect(shared).toContain("--chart-bollinger-band: var(--up);");
    expect(shared).toContain("--chart-supertrend-up: var(--up);");
    expect(shared).toContain("--chart-supertrend-down: var(--down);");
    expect(shared).toContain("--chart-grid: var(--hair);");
    expect(shared).toContain("--chart-axis: var(--ink-mute);");
  });

  it("snapshots the dark pair the guard already accepts", () => {
    const dark = tokens.slice(
      tokens.indexOf(':root[data-theme="dark"]'),
      tokens.indexOf(':root[data-theme="light"]'),
    );
    expect(tokens).toMatch(/--accent-digiquant:\s+#3dd6c4/i);
    expect(dark).toContain("--up:   var(--accent-digiquant);");
    expect(dark).toContain("--down: #E5533E;");
    expect(DIGIQUANT_CHART.candleUp).toBe("#3DD6C4");
    expect(DIGIQUANT_CHART.candleDown).toBe("#E5533E");
    expect(DIGIQUANT_CHART.volumeUp).toBe(DIGIQUANT_CHART.candleUp);
    expect(DIGIQUANT_CHART.volumeDown).toBe(DIGIQUANT_CHART.candleDown);
    expect(DIGIQUANT_CHART.sma).toBe(DIGIQUANT_CHART.candleUp);
    expect(DIGIQUANT_CHART.ema).toBe(DIGIQUANT_CHART.candleDown);
    expect(readDigiquantChartScale(null)).toEqual(DIGIQUANT_CHART);
  });
});
