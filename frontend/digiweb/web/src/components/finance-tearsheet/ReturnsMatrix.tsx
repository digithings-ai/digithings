/**
 * ReturnsMatrix (#1463) — the period matrix promoted verbatim from
 * frontend/digiquant-web/components/tearsheet/charts.tsx: 3 metrics
 * (return / drawdown / volatility) x 3 granularities (monthly / quarterly /
 * annual), derived from the equity curve (returns, vol) or the drawdown
 * curve (max DD per slot). Cells tint by data-driven max-abs magnitude on
 * the money tokens; returns format as signed compact % so crypto-scale
 * figures (hundreds / thousands of %) fit the narrow cells; the trailing
 * Year column compounds. This is THE matrix grammar — the former
 * finance-charts MonthlyReturns (fixed-peak tint, unsigned 1-dp cells,
 * arithmetic-sum totals) was deprecated into it (monthly slice =
 * `period="monthly" metric="return"`).
 */
import { fmtCompact } from "./format";
import { annualizedVolPct, dailyReturnsFromEquity } from "./stats";
import { type TearsheetSeriesPoint } from "./types";

export type ReturnsPeriod = "monthly" | "quarterly" | "annual";
export type MatrixMetric = "return" | "drawdown" | "volatility";

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const QUARTER_LABELS = ["Q1", "Q2", "Q3", "Q4"];

/** A single rendered cell value (or null = no data in that slot). */
interface MatrixCell {
  value: number | null;
}
interface MatrixRow {
  year: number;
  cells: MatrixCell[];
  yearValue: number | null;
}

/** Number of columns per granularity (the trailing Year column is separate). */
function colCount(period: ReturnsPeriod): number {
  return period === "monthly" ? 12 : period === "quarterly" ? 4 : 1;
}

function slotOf(month: number, period: ReturnsPeriod): number {
  return period === "monthly" ? month : period === "quarterly" ? Math.floor(month / 3) : 0;
}

function bucketEquityBySlot(points: TearsheetSeriesPoint[], period: ReturnsPeriod) {
  const lastInSlot = new Map<string, number>();
  const pointsInSlot = new Map<string, TearsheetSeriesPoint[]>();
  const yearLast = new Map<number, number>();
  let minYear = Infinity;
  let maxYear = -Infinity;

  for (const p of points) {
    const d = new Date(p.t);
    const year = d.getUTCFullYear();
    const slot = slotOf(d.getUTCMonth(), period);
    const key = `${year}:${slot}`;
    lastInSlot.set(key, p.v);
    const bucket = pointsInSlot.get(key) ?? [];
    bucket.push(p);
    pointsInSlot.set(key, bucket);
    yearLast.set(year, p.v);
    if (year < minYear) minYear = year;
    if (year > maxYear) maxYear = year;
  }
  return { lastInSlot, pointsInSlot, yearLast, minYear, maxYear };
}

function bucketDrawdownBySlot(points: TearsheetSeriesPoint[], period: ReturnsPeriod) {
  const minInSlot = new Map<string, number>();
  const yearMin = new Map<number, number>();
  let minYear = Infinity;
  let maxYear = -Infinity;

  for (const p of points) {
    const d = new Date(p.t);
    const year = d.getUTCFullYear();
    const slot = slotOf(d.getUTCMonth(), period);
    const key = `${year}:${slot}`;
    const prev = minInSlot.get(key);
    minInSlot.set(key, prev === undefined ? p.v : Math.min(prev, p.v));
    const yPrev = yearMin.get(year);
    yearMin.set(year, yPrev === undefined ? p.v : Math.min(yPrev, p.v));
    if (year < minYear) minYear = year;
    if (year > maxYear) maxYear = year;
  }
  return { minInSlot, yearMin, minYear, maxYear };
}

/**
 * Period matrix from equity (returns, vol) or drawdown curve (max DD per slot).
 */
function buildMatrixRows(
  equity: TearsheetSeriesPoint[],
  drawdown: TearsheetSeriesPoint[] | undefined,
  period: ReturnsPeriod,
  metric: MatrixMetric,
): MatrixRow[] {
  if (!equity || equity.length === 0) return [];
  const cols = colCount(period);

  if (metric === "drawdown") {
    if (!drawdown || drawdown.length === 0) return [];
    const { minInSlot, yearMin, minYear, maxYear } = bucketDrawdownBySlot(drawdown, period);
    if (!Number.isFinite(minYear)) return [];
    const rows: MatrixRow[] = [];
    for (let year = minYear; year <= maxYear; year++) {
      const cells: MatrixCell[] = [];
      for (let s = 0; s < cols; s++) {
        const v = minInSlot.get(`${year}:${s}`);
        cells.push({ value: v === undefined ? null : v });
      }
      const yv = yearMin.get(year);
      rows.push({ year, cells, yearValue: yv === undefined ? null : yv });
    }
    return rows;
  }

  const { lastInSlot, pointsInSlot, yearLast, minYear, maxYear } = bucketEquityBySlot(
    equity,
    period,
  );
  if (!Number.isFinite(minYear)) return [];

  if (metric === "volatility") {
    const rows: MatrixRow[] = [];
    for (let year = minYear; year <= maxYear; year++) {
      const cells: MatrixCell[] = [];
      for (let s = 0; s < cols; s++) {
        const pts = pointsInSlot.get(`${year}:${s}`);
        const vol =
          pts && pts.length >= 2 ? annualizedVolPct(dailyReturnsFromEquity(pts)) : null;
        cells.push({ value: vol });
      }
      const yearPts = equity.filter((p) => new Date(p.t).getUTCFullYear() === year);
      const yearVol =
        yearPts.length >= 2 ? annualizedVolPct(dailyReturnsFromEquity(yearPts)) : null;
      rows.push({ year, cells, yearValue: yearVol });
    }
    return rows;
  }

  const opening = equity[0].v;
  const rows: MatrixRow[] = [];
  let prevClose = opening;

  for (let year = minYear; year <= maxYear; year++) {
    const cells: MatrixCell[] = [];
    for (let s = 0; s < cols; s++) {
      const close = lastInSlot.get(`${year}:${s}`);
      if (close === undefined) {
        cells.push({ value: null });
      } else {
        const ret = prevClose > 0 ? (close / prevClose - 1) * 100 : null;
        cells.push({ value: ret });
        prevClose = close;
      }
    }
    const last = yearLast.get(year);
    const yearValue =
      last !== undefined && prevCloseAtYearStart(year, minYear, opening, yearLast) > 0
        ? (last / prevCloseAtYearStart(year, minYear, opening, yearLast) - 1) * 100
        : null;
    rows.push({ year, cells, yearValue: yearValue });
  }
  return rows;
}

/** Equity carried into `year`: the prior year's last close, or the opening for the
 *  first year. Keeps the Year column consistent with the chained cell logic. */
function prevCloseAtYearStart(year: number, minYear: number, opening: number, yearLast: Map<number, number>): number {
  if (year === minYear) return opening;
  // Walk back to the most recent prior year that actually has data.
  for (let y = year - 1; y >= minYear; y--) {
    const v = yearLast.get(y);
    if (v !== undefined) return v;
  }
  return opening;
}

/** Inline cell background: tone-coloured with alpha scaled by |value| relative to max-abs. */
function cellBg(value: number | null, maxAbs: number, metric: MatrixMetric): string {
  if (value === null) return "transparent";
  if (value === 0 && metric === "return") return "transparent";
  const tone =
    metric === "drawdown" || metric === "volatility"
      ? "var(--down)"
      : value > 0
        ? "var(--up)"
        : "var(--down)";
  const mag = maxAbs > 0 ? Math.abs(value) / maxAbs : 0;
  const pct = Math.round(14 + Math.min(1, mag) * 58);
  return `color-mix(in srgb, ${tone} ${pct}%, transparent)`;
}

/** Compact cell % — sheds decimals as magnitude grows so wide crypto returns
 *  (hundreds / thousands of %) fit the narrow grid cells without truncation. */
function fmtCellPct(v: number): string {
  const a = Math.abs(v);
  if (a >= 1000) return fmtCompact(v) + "%";
  if (a >= 100) return v.toFixed(0) + "%";
  return v.toFixed(1) + "%";
}

function fmtCellValue(v: number | null, metric: MatrixMetric): string {
  if (v === null) return "";
  if (metric === "volatility") return v.toFixed(1) + "%";
  return fmtCellPct(v);
}

/**
 * Calendar heatmap of period returns derived from the equity curve. Rows = years,
 * columns = months / quarters / a single annual cell, plus a trailing compounded
 * "Year" column. Pure CSS-grid table (no SVG) so it reflows and scrolls on mobile.
 */
export function ReturnsMatrix({
  points,
  drawdown,
  period,
  metric = "return",
}: {
  points: TearsheetSeriesPoint[];
  drawdown?: TearsheetSeriesPoint[];
  period: ReturnsPeriod;
  metric?: MatrixMetric;
}) {
  const rows = buildMatrixRows(points, drawdown, period, metric);
  if (rows.length === 0) {
    return (
      <div className="ts-status">
        {metric === "drawdown" && !drawdown?.length ? "drawdown data unavailable" : "no data"}
      </div>
    );
  }

  const cols = colCount(period);
  const labels = period === "monthly" ? MONTH_LABELS : period === "quarterly" ? QUARTER_LABELS : ["Year"];
  const showYearCol = period !== "annual";

  let maxAbs = 0;
  for (const r of rows) {
    for (const c of r.cells) if (c.value !== null) maxAbs = Math.max(maxAbs, Math.abs(c.value));
    if (showYearCol && r.yearValue !== null) maxAbs = Math.max(maxAbs, Math.abs(r.yearValue));
  }

  const gridTemplate = `minmax(3rem, auto) repeat(${cols + (showYearCol ? 1 : 0)}, minmax(0, 1fr))`;
  const metricLabel = metric === "return" ? "returns" : metric === "drawdown" ? "drawdown" : "volatility";

  return (
    <div className="ts-table-wrap ts-matrix-wrap">
      <div
        className="ts-matrix ts-matrix-fill"
        style={{ gridTemplateColumns: gridTemplate }}
        role="table"
        aria-label={`${period} ${metricLabel}`}
      >
        <div className="ts-matrix-corner" role="columnheader" />
        {labels.map((l) => (
          <div key={l} className="ts-matrix-head" role="columnheader">{l}</div>
        ))}
        {showYearCol ? <div className="ts-matrix-head ts-matrix-year-head" role="columnheader">Year</div> : null}
        {rows.map((r) => (
          <div key={r.year} className="ts-matrix-row" role="row" style={{ display: "contents" }}>
            <div className="ts-matrix-rowlabel" role="rowheader">{r.year}</div>
            {r.cells.map((c, i) => (
              <div
                key={i}
                className={"ts-matrix-cell" + (c.value === null ? " is-empty" : "")}
                style={{ background: cellBg(c.value, maxAbs, metric) }}
                role="cell"
                title={
                  c.value === null
                    ? "no data"
                    : `${labels[i]} ${r.year}: ${fmtCellValue(c.value, metric)}`
                }
              >
                {fmtCellValue(c.value, metric)}
              </div>
            ))}
            {showYearCol ? (
              <div
                className={"ts-matrix-cell ts-matrix-year" + (r.yearValue === null ? " is-empty" : "")}
                style={{ background: cellBg(r.yearValue, maxAbs, metric) }}
                role="cell"
                title={
                  r.yearValue === null
                    ? "no data"
                    : `${r.year} total: ${fmtCellValue(r.yearValue, metric)}`
                }
              >
                {fmtCellValue(r.yearValue, metric)}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
