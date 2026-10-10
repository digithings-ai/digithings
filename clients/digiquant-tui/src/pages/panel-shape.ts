/** Which catalog blocks can be drawn as a chart, and from which fields of the official read.
 *  A block that is not in the map stays a table. Web and TUI read the same map. */

export type PanelShape = "series" | "composition" | "ranking";
export type ChartType = "line" | "area" | "bar" | "donut" | "treemap";
export type PanelMode = "table" | "chart";
export type PanelUnit = "index" | "pct" | "bp";

export type PanelSpec = {
  shape: PanelShape;
  /** Key of the row array inside `data`. */
  rows: string;
  /** Row field for the x axis or the slice label. */
  label: string;
  /** Row field for the plotted number. */
  value: string;
  unit: PanelUnit;
  /** What the pane shows first. */
  mode: PanelMode;
  /** First chart type. Must be in `CHART_TYPES[shape]`. */
  chart: ChartType;
};

/** Chart types each shape allows, in picker order. */
export const CHART_TYPES: Record<PanelShape, readonly ChartType[]> = {
  series: ["line", "area", "bar"],
  composition: ["donut", "bar", "treemap"],
  ranking: ["bar"],
};

export const CHART_LABEL: Record<ChartType, string> = {
  line: "Line",
  area: "Area",
  bar: "Bar",
  donut: "Donut",
  treemap: "Treemap",
};

const spec = (
  shape: PanelShape,
  rows: string,
  label: string,
  value: string,
  unit: PanelUnit,
  mode: PanelMode,
  chart: ChartType = CHART_TYPES[shape][0] ?? "bar",
): PanelSpec => ({ shape, rows, label, value, unit, mode, chart });

/** Block id → panel shape. NAV plots the chained index, never raw nav. */
export const PANEL_SHAPES: Record<string, PanelSpec> = {
  nav: spec("series", "points", "date", "index", "index", "chart"),
  navtable: spec("series", "points", "date", "index", "index", "table"),
  drawdown: spec("series", "series", "t", "v", "pct", "chart", "area"),
  "rt-curve": spec("series", "curve", "tenor", "yield_pct", "pct", "chart"),
  sleeves: spec("composition", "sleeves", "sleeve", "weight_pct", "pct", "chart"),
  book: spec("composition", "rows", "ticker", "weight_pct", "pct", "table"),
  holdings: spec("composition", "rows", "ticker", "scaled_weight_pct", "pct", "table"),
  movers: spec("ranking", "rows", "ticker", "day_return_pct", "pct", "table"),
  attribution: spec("ranking", "names", "ticker", "contribution_bp", "bp", "chart"),
};

export type PanelPoint = { label: string; value: number };

export type PanelData = {
  spec: PanelSpec;
  points: PanelPoint[];
  /** Chart types that can draw these points. Donut and treemap need no negative value. */
  charts: ChartType[];
};

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The plottable points for one block, or null when the block stays a table.
 *  A null value is dropped, not drawn as zero. Fewer than two points is not a chart. */
export function panelData(id: string, data: unknown): PanelData | null {
  const spec = PANEL_SHAPES[id];
  if (!spec) return null;
  const rows = record(data)?.[spec.rows];
  if (!Array.isArray(rows)) return null;

  let points: PanelPoint[] = [];
  for (const raw of rows) {
    const row = record(raw);
    if (!row || row.is_cash === true) continue;
    const label = row[spec.label];
    const value = finite(row[spec.value]);
    if (typeof label !== "string" || label.length === 0 || value === null) continue;
    points.push({ label, value });
  }
  if (spec.shape !== "series") points = [...points].sort((a, b) => b.value - a.value);
  if (points.length < 2) return null;

  const signed = points.some((point) => point.value < 0);
  const charts = CHART_TYPES[spec.shape].filter((type) => !(signed && (type === "donut" || type === "treemap")));
  return { spec, points, charts };
}

/** Names a chart labels row by row, at most. A series is never cut. */
export const CHART_NAMES = 12;

/** The points one chart draws. A long ranking keeps both ends; a long composition keeps the largest. */
export function chartPoints(panel: PanelData, max = CHART_NAMES): { points: PanelPoint[]; hidden: number } {
  const { points, spec } = panel;
  if (spec.shape === "series" || points.length <= max) return { points, hidden: 0 };
  if (spec.shape === "ranking") {
    const head = Math.ceil(max / 2);
    return { points: [...points.slice(0, head), ...points.slice(points.length - (max - head))], hidden: points.length - max };
  }
  return { points: points.slice(0, max), hidden: points.length - max };
}

/** The chart type to draw: the saved pick when it still fits, else the block's first chart. */
export function chartFor(panel: PanelData, picked: ChartType | null | undefined): ChartType {
  if (picked && panel.charts.includes(picked)) return picked;
  if (panel.charts.includes(panel.spec.chart)) return panel.spec.chart;
  return panel.charts[0] ?? "bar";
}
