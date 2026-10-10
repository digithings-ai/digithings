import type { EChartsOption } from "echarts";
import type { OHLCV, VelaOptions } from "@luxalgo/vela";
import {
  dayOf,
  monthlyReturns,
  type ChartType,
  type PanelPoint,
  type PanelShape,
  type PanelUnit,
} from "../../../../clients/digiquant-tui/src/pages/panel-shape";

/** Which library draws a panel. Vela draws price views: an index level over dates, as a line or an area.
 *  ECharts draws the rest: bars, donut, treemap, heatmap, and any series that is not a price. */
export type ChartEngine = "vela" | "echarts";

/** Canvas cannot read CSS variables, so the chart reads the desk tokens once at mount. */
export type ChartInk = { ink: string; mute: string; hair: string; up: string; down: string; surface: string; font: string };

export const FALLBACK_INK: ChartInk = {
  ink: "#eceef0",
  mute: "#7d8389",
  hair: "rgba(255, 255, 255, 0.09)",
  up: "#3dd6c4",
  down: "#e5533e",
  surface: "#000000",
  font: "monospace",
};

/** Slice fills step down from ink so neighbours stay apart without a palette. */
const SLICE = [1, 0.72, 0.52, 0.38, 0.28, 0.2];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FONT_SIZE = 10;

export function unitText(value: number, unit: PanelUnit): string {
  if (unit === "pct") return `${value.toFixed(2)}%`;
  if (unit === "bp") return `${value.toFixed(1)} bp`;
  return value.toFixed(2);
}

/** `color` at `alpha`. A hex or rgb() token is mixed; anything else is returned as is. */
export function withAlpha(color: string, alpha: number): string {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(color.trim());
  if (hex) {
    const digits = hex[1] ?? "";
    const full = digits.length === 3 ? [...digits].map((d) => d + d).join("") : digits;
    const [r, g, b] = [0, 2, 4].map((at) => parseInt(full.slice(at, at + 2), 16));
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  const rgb = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(color.trim());
  if (rgb) return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${alpha})`;
  return color;
}

export function chartEngine(unit: PanelUnit, type: ChartType, points: PanelPoint[]): ChartEngine {
  const price = unit === "index" && (type === "line" || type === "area");
  return price && points.every((point) => dayOf(point.label) !== null) ? "vela" : "echarts";
}

/** One flat bar per day: open, high, low and close all carry the level. A repeated day keeps its last level. */
export function velaBars(points: PanelPoint[]): OHLCV[] {
  const byDay = new Map<number, number>();
  for (const point of points) {
    const time = dayOf(point.label);
    if (time !== null) byDay.set(time, point.value);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([time, value]) => ({ time, open: value, high: value, low: value, close: value }));
}

export function velaOptions(type: "line" | "area", points: PanelPoint[], ink: ChartInk, reduced: boolean): VelaOptions {
  return {
    symbol: "INDEX",
    timeframe: "D",
    live: false,
    data: velaBars(points),
    priceStyle: type,
    theme: {
      background: ink.surface,
      textColor: ink.mute,
      gridColor: "rgba(0, 0, 0, 0)",
      borderColor: ink.hair,
      upColor: ink.up,
      downColor: ink.down,
      fontFamily: ink.font,
    },
    upColor: ink.up,
    downColor: ink.down,
    volume: false,
    drawings: false,
    animations: reduced ? false : { intro: true, zoom: true, pan: true },
  };
}

/** Line and area in ink, no gridlines. Applied through `chart.renderer.applyConfig`. */
export function velaConfig(ink: ChartInk) {
  return {
    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    line: { color: ink.ink, width: 2 },
    area: { lineColor: ink.ink, width: 2, topColor: withAlpha(ink.ink, 0.18), bottomColor: withAlpha(ink.ink, 0.02) },
  };
}

function base(ink: ChartInk, reduced: boolean): EChartsOption {
  return {
    backgroundColor: "transparent",
    animation: !reduced,
    textStyle: { fontFamily: ink.font, fontSize: FONT_SIZE, color: ink.mute },
    tooltip: {
      backgroundColor: ink.surface,
      borderColor: ink.hair,
      borderWidth: 1,
      padding: [4, 6],
      textStyle: { fontFamily: ink.font, fontSize: FONT_SIZE, color: ink.ink },
      confine: true,
    },
  };
}

const AXIS_LINE = (ink: ChartInk) => ({ show: true, lineStyle: { color: ink.hair } });

/** `2026-07-06` reads `Jul 6`; a tenor or any other label stays as it is. */
function shortDay(label: string): string {
  const time = dayOf(label);
  if (time === null) return label;
  const day = new Date(time);
  return `${MONTHS[day.getUTCMonth()]} ${day.getUTCDate()}`;
}

function signColor(value: number, ink: ChartInk): string {
  return value < 0 ? ink.down : ink.up;
}

function sliceColor(index: number, ink: ChartInk): string {
  return withAlpha(ink.ink, SLICE[index % SLICE.length] ?? 1);
}

/** A series that is not a price: one column or point per date or tenor. */
function seriesOption(type: ChartType, points: PanelPoint[], unit: PanelUnit, ink: ChartInk, reduced: boolean): EChartsOption {
  const format = (value: unknown) => unitText(Number(value), unit);
  const bar = type === "bar";
  return {
    ...base(ink, reduced),
    tooltip: { ...base(ink, reduced).tooltip, trigger: "axis", axisPointer: { type: "line", lineStyle: { color: ink.hair } }, valueFormatter: format },
    grid: { left: 4, right: 8, top: 8, bottom: 4 },
    xAxis: {
      type: "category",
      data: points.map((point) => point.label),
      boundaryGap: bar,
      axisLine: AXIS_LINE(ink),
      axisTick: { show: false },
      axisLabel: { color: ink.mute, hideOverlap: true, formatter: shortDay },
    },
    yAxis: {
      type: "value",
      scale: type === "line",
      splitLine: { show: false },
      axisLine: AXIS_LINE(ink),
      axisLabel: { color: ink.mute, formatter: format },
    },
    series: [
      bar
        ? {
            type: "bar",
            barCategoryGap: "20%",
            data: points.map((point) => ({ value: point.value, itemStyle: { color: signColor(point.value, ink) } })),
          }
        : {
            type: "line",
            showSymbol: false,
            data: points.map((point) => point.value),
            lineStyle: { color: ink.ink, width: 2 },
            itemStyle: { color: ink.ink },
            ...(type === "area" ? { areaStyle: { color: withAlpha(ink.ink, 0.14) } } : {}),
          },
    ],
  };
}

/** One labelled row per name, largest first, signed bars from zero. */
function rowBars(points: PanelPoint[], unit: PanelUnit, ink: ChartInk, reduced: boolean): EChartsOption {
  const format = (value: unknown) => unitText(Number(value), unit);
  return {
    ...base(ink, reduced),
    tooltip: { ...base(ink, reduced).tooltip, trigger: "item", valueFormatter: format },
    grid: { left: 4, right: 56, top: 4, bottom: 4 },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      inverse: true,
      data: points.map((point) => point.label),
      axisLine: AXIS_LINE(ink),
      axisTick: { show: false },
      axisLabel: { color: ink.mute },
    },
    series: [
      {
        type: "bar",
        barCategoryGap: "30%",
        data: points.map((point) => ({
          value: point.value,
          itemStyle: { color: signColor(point.value, ink) },
          label: { show: true, position: "right", color: ink.ink, formatter: () => unitText(point.value, unit) },
        })),
      },
    ],
  };
}

/** Below this width a pane drops the donut legend and the heatmap cell numbers; the tooltip and the table keep them. */
export const NARROW_PX = 320;

function donut(points: PanelPoint[], unit: PanelUnit, ink: ChartInk, reduced: boolean): EChartsOption {
  const values = new Map(points.map((point) => [point.label, point.value]));
  return {
    ...base(ink, reduced),
    media: [{ query: { maxWidth: NARROW_PX }, option: { legend: { show: false }, series: [{ center: ["50%", "50%"] }] } }],
    tooltip: { ...base(ink, reduced).tooltip, trigger: "item", valueFormatter: (value) => unitText(Number(value), unit) },
    legend: {
      orient: "vertical",
      right: 4,
      top: "middle",
      icon: "rect",
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 6,
      textStyle: { color: ink.mute, fontFamily: ink.font, fontSize: FONT_SIZE },
      formatter: (name: string) => `${name}  ${unitText(values.get(name) ?? 0, unit)}`,
    },
    series: [
      {
        type: "pie",
        radius: ["55%", "85%"],
        center: ["28%", "50%"],
        avoidLabelOverlap: true,
        label: { show: false },
        itemStyle: { borderColor: ink.surface, borderWidth: 2 },
        data: points.map((point, index) => ({ name: point.label, value: point.value, itemStyle: { color: sliceColor(index, ink) } })),
      },
    ],
  };
}

function treemap(points: PanelPoint[], unit: PanelUnit, ink: ChartInk, reduced: boolean): EChartsOption {
  return {
    ...base(ink, reduced),
    tooltip: { ...base(ink, reduced).tooltip, trigger: "item", valueFormatter: (value) => unitText(Number(value), unit) },
    series: [
      {
        type: "treemap",
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        width: "100%",
        height: "100%",
        top: 0,
        left: 0,
        itemStyle: { borderColor: ink.surface, borderWidth: 0, gapWidth: 2 },
        data: points.map((point, index) => ({
          name: point.label,
          value: point.value,
          itemStyle: { color: sliceColor(index, ink) },
          label: {
            color: (SLICE[index % SLICE.length] ?? 1) >= 0.52 ? ink.surface : ink.ink,
            fontFamily: ink.font,
            fontSize: FONT_SIZE,
            formatter: () => `${point.label}\n${unitText(point.value, unit)}`,
          },
        })),
      },
    ],
  };
}

/** Month-on-month change of the index: years down, months across. Down and up poles, a neutral middle. */
function heatmap(points: PanelPoint[], ink: ChartInk, reduced: boolean): EChartsOption {
  const months = monthlyReturns(points);
  const years = [...new Set(months.map((month) => month.year))].sort((a, b) => a - b);
  const reach = Math.max(...months.map((month) => Math.abs(month.pct)), 0.01);
  return {
    ...base(ink, reduced),
    tooltip: {
      ...base(ink, reduced).tooltip,
      trigger: "item",
      formatter: (params) => {
        const value = (Array.isArray(params) ? params[0]?.value : params.value) as number[] | undefined;
        if (!value) return "";
        return `${MONTHS[value[0] ?? 0]} ${years[value[1] ?? 0]}  ${unitText(value[2] ?? 0, "pct")}`;
      },
    },
    media: [{ query: { maxWidth: NARROW_PX }, option: { series: [{ label: { show: false } }] } }],
    grid: { left: 4, right: 4, top: 4, bottom: 4 },
    xAxis: { type: "category", data: MONTHS, axisLine: AXIS_LINE(ink), axisTick: { show: false }, axisLabel: { color: ink.mute }, splitArea: { show: false } },
    yAxis: { type: "category", data: years.map(String), axisLine: AXIS_LINE(ink), axisTick: { show: false }, axisLabel: { color: ink.mute } },
    visualMap: { show: false, min: -reach, max: reach, dimension: 2, inRange: { color: [ink.down, withAlpha(ink.ink, 0.12), ink.up] } },
    series: [
      {
        type: "heatmap",
        data: months.map((month) => [month.month - 1, years.indexOf(month.year), Number(month.pct.toFixed(4))]),
        label: { show: true, color: ink.ink, fontFamily: ink.font, fontSize: FONT_SIZE, formatter: (params) => (params.value as number[])[2]?.toFixed(1) ?? "" },
        itemStyle: { borderColor: ink.surface, borderWidth: 2 },
      },
    ],
  };
}

/** A series bar is a column per date or tenor. A composition or ranking bar is one labelled row per name. */
export function echartsOption(
  shape: PanelShape,
  type: ChartType,
  points: PanelPoint[],
  unit: PanelUnit,
  ink: ChartInk,
  reduced: boolean,
): EChartsOption {
  if (type === "heatmap") return heatmap(points, ink, reduced);
  if (type === "donut") return donut(points, unit, ink, reduced);
  if (type === "treemap") return treemap(points, unit, ink, reduced);
  if (type === "bar" && shape !== "series") return rowBars(points, unit, ink, reduced);
  return seriesOption(type, points, unit, ink, reduced);
}
