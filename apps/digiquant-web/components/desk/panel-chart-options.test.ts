import { describe, expect, it } from "vitest";
import { CHART_TYPES, type ChartType, type PanelUnit } from "../../../../clients/digiquant-tui/src/pages/panel-shape";
import { FALLBACK_INK, chartEngine, echartsOption, velaBars, velaConfig, velaOptions, withAlpha } from "./panel-chart-options";

const nav = [
  { label: "2026-08-31", value: 100 },
  { label: "2026-09-30", value: 102 },
  { label: "2026-09-30", value: 102.5 },
  { label: "2026-10-09", value: 99.37 },
];
const names = [
  { label: "UUP", value: 29.97 },
  { label: "DBO", value: 4.72 },
  { label: "XLV", value: -1.5 },
];

describe("chartEngine", () => {
  it("sends an index level over dates, as a line or an area, to Vela", () => {
    expect(chartEngine("index", "line", nav)).toBe("vela");
    expect(chartEngine("index", "area", nav)).toBe("vela");
  });

  it("sends bars, heatmaps, percent series and non-date series to ECharts", () => {
    expect(chartEngine("index", "bar", nav)).toBe("echarts");
    expect(chartEngine("index", "heatmap", nav)).toBe("echarts");
    expect(chartEngine("pct", "area", nav)).toBe("echarts");
    expect(chartEngine("index", "line", [{ label: "2Y", value: 1 }, { label: "10Y", value: 2 }])).toBe("echarts");
  });
});

describe("Vela price view", () => {
  it("plots the level as flat daily bars in date order, one per day", () => {
    const bars = velaBars([...nav].reverse());
    expect(bars.map((bar) => bar.close)).toEqual([100, 102, 99.37]);
    for (const bar of bars) expect([bar.open, bar.high, bar.low]).toEqual([bar.close, bar.close, bar.close]);
    expect(bars[0]?.time).toBe(Date.UTC(2026, 7, 31));
  });

  it("is a static chart with no volume, drawings or gridlines, and no motion when reduced", () => {
    const options = velaOptions("area", nav, FALLBACK_INK, true);
    expect(options).toMatchObject({ live: false, volume: false, drawings: false, priceStyle: "area", animations: false });
    expect(velaConfig(FALLBACK_INK).grid).toEqual({ vertLines: { visible: false }, horzLines: { visible: false } });
  });
});

describe("ECharts options", () => {
  it("builds every shape and type with finite numbers only", () => {
    for (const shape of Object.keys(CHART_TYPES) as (keyof typeof CHART_TYPES)[]) {
      for (const type of CHART_TYPES[shape] as readonly ChartType[]) {
        const points = shape === "series" ? nav : names.filter((point) => type === "bar" || point.value > 0);
        const unit: PanelUnit = shape === "series" ? "index" : "pct";
        const json = JSON.stringify(echartsOption(shape, type, points, unit, FALLBACK_INK, false));
        expect(json, `${shape}/${type}`).not.toMatch(/NaN|Infinity|null/);
      }
    }
  });

  it("colours a ranking bar by sign and keeps text in ink", () => {
    const option = echartsOption("ranking", "bar", names, "bp", FALLBACK_INK, false) as { series: { data: { itemStyle: { color: string }; label: { color: string } }[] }[] };
    const data = option.series[0]?.data ?? [];
    expect(data.map((item) => item.itemStyle.color)).toEqual([FALLBACK_INK.up, FALLBACK_INK.up, FALLBACK_INK.down]);
    expect(new Set(data.map((item) => item.label.color))).toEqual(new Set([FALLBACK_INK.ink]));
  });

  it("lays the heatmap out as months across and years down, from the NAV index", () => {
    const option = echartsOption("series", "heatmap", nav, "index", FALLBACK_INK, false) as {
      series: { data: number[][] }[];
      yAxis: { data: string[] };
    };
    expect(option.yAxis.data).toEqual(["2026"]);
    expect(option.series[0]?.data).toEqual([
      [7, 0, 0],
      [8, 0, 2.5],
      [9, 0, Number(((99.37 / 102.5 - 1) * 100).toFixed(4))],
    ]);
  });
});

describe("withAlpha", () => {
  it("mixes hex and rgb tokens and leaves anything else alone", () => {
    expect(withAlpha("#fff", 0.5)).toBe("rgba(255, 255, 255, 0.5)");
    expect(withAlpha("#3dd6c4", 0.2)).toBe("rgba(61, 214, 196, 0.2)");
    expect(withAlpha("rgba(255, 255, 255, 0.09)", 0.3)).toBe("rgba(255, 255, 255, 0.3)");
    expect(withAlpha("oklch(0.9 0 0)", 0.3)).toBe("oklch(0.9 0 0)");
  });
});
