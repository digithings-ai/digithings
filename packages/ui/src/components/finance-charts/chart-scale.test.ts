import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DIGIQUANT_CHART, readDigiquantChartScale } from "./chart-scale";

const tokens = readFileSync(new URL("../../../../design/tokens.css", import.meta.url), "utf8");

const INDICATOR_TOKEN = {
  sma: "--chart-sma",
  ema: "--chart-ema",
  vwap: "--chart-vwap",
  bollinger: "--chart-bollinger",
  bollingerBand: "--chart-bollinger-band",
  supertrendUp: "--chart-supertrend-up",
  supertrendDown: "--chart-supertrend-down",
} as const;

const DARK_INDICATORS = {
  sma: "#1EC98A",
  ema: "#5AD4F0",
  vwap: "#F0D44A",
  bollinger: "#B0DC3A",
  bollingerBand: "#F09238",
  supertrendUp: "#54DC62",
  supertrendDown: "#6A96F0",
} as const;

const LIGHT_INDICATORS = {
  sma: "#187E58",
  ema: "#1B798E",
  vwap: "#806E18",
  bollinger: "#5D7817",
  bollingerBand: "#A15F1F",
  supertrendUp: "#1A8025",
  supertrendDown: "#3369D8",
} as const;

describe("digiquant chart scale", () => {
  it("aliases candles and volume to the canon up and down pair", () => {
    const shared = tokens.slice(tokens.indexOf(":root[data-theme] {"));
    expect(shared).toContain("--chart-candle-up: var(--up);");
    expect(shared).toContain("--chart-candle-down: var(--down);");
    expect(shared).toContain("--chart-volume-up: var(--up);");
    expect(shared).toContain("--chart-volume-down: var(--down);");
    expect(shared).toContain("--chart-grid: var(--hair);");
    expect(shared).toContain("--chart-axis: var(--ink-mute);");
    expect(shared).not.toContain("--chart-sma: var(--up);");
    expect(shared).not.toContain("--chart-ema: var(--down);");
  });

  it("gives each study its own hue from the teal-led palette", () => {
    const dark = tokens.slice(
      tokens.indexOf(':root[data-theme="dark"]'),
      tokens.indexOf(':root[data-theme="light"]'),
    );
    const light = tokens.slice(
      tokens.indexOf(':root[data-theme="light"]'),
      tokens.indexOf(":root[data-theme] {"),
    );
    for (const role of Object.keys(INDICATOR_TOKEN) as (keyof typeof INDICATOR_TOKEN)[]) {
      const decl = `${INDICATOR_TOKEN[role]}:`;
      expect(dark).toContain(`${decl} ${DARK_INDICATORS[role]};`);
      expect(light).toContain(`${decl} ${LIGHT_INDICATORS[role]};`);
    }
    const snapshot = [
      DIGIQUANT_CHART.sma,
      DIGIQUANT_CHART.ema,
      DIGIQUANT_CHART.vwap,
      DIGIQUANT_CHART.bollingerBasis,
      DIGIQUANT_CHART.bollingerBand,
      DIGIQUANT_CHART.supertrendUp,
      DIGIQUANT_CHART.supertrendDown,
    ];
    expect(snapshot).toEqual(Object.values(DARK_INDICATORS));
    expect(new Set(snapshot).size).toBe(snapshot.length);
    for (const hex of snapshot) {
      expect(hex).not.toBe(DIGIQUANT_CHART.candleUp);
      expect(hex).not.toBe(DIGIQUANT_CHART.candleDown);
    }
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
    expect(readDigiquantChartScale(null)).toEqual(DIGIQUANT_CHART);
  });
});
