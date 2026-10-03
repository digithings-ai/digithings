import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Tearsheet panes. A chart is the NAV numbers the series already returned. */
const BARS = "▁▂▃▄▅▆▇█";
const CHART_WIDTH = 24;

function rec(value: unknown): Record<string, unknown> | null {
  return value != null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function cell(value: unknown): string {
  if (value == null || value === "") return DASH;
  if (typeof value === "number") return Number.isFinite(value) ? JSON.stringify(value) : DASH;
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  return DASH;
}

function stat(pairs: [string, string][]): PaneBlock | null {
  const shown = pairs.filter(([, value]) => value !== DASH);
  if (shown.length === 0) return null;
  return { kind: "stat", text: shown.map(([label, value]) => `${label}  ${value}`).join("   ") };
}

function table(columns: string[], rows: string[][]): PaneBlock | null {
  if (rows.length === 0) return null;
  return { kind: "table", columns, rows };
}

function sentence(text: string): PaneBody {
  return { blocks: [{ kind: "sentence", text }] };
}

function bodyOf(blocks: PaneBlock[]): PaneBody {
  return { blocks: blocks.length > 0 ? blocks : [{ kind: "sentence", text: EMPTY_READ }] };
}

function textBody(result: ReadResult): PaneBody {
  const lines = result.lines.filter((line) => line.length > 0);
  return shapeLines(lines.length > 0 ? lines : [EMPTY_READ]);
}

function withProvenance(result: ReadResult, painted: PaneBody): PaneBody {
  const only = painted.blocks.length === 1 ? painted.blocks[0] : null;
  if (only?.kind === "sentence") return painted;
  const bits = result.lines.filter((line) => line.startsWith("source  ") || line.startsWith("marks  "));
  if (bits.length === 0) return painted;
  return { blocks: [{ kind: "stat", text: bits.join("   ") }, ...painted.blocks] };
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function named(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Evenly spaced points from the series. Each bar is a value the payload returned. */
function sample(values: number[], width: number): number[] {
  if (values.length <= width) return values;
  const last = values.length - 1;
  const out: number[] = [];
  for (let i = 0; i < width; i += 1) {
    const value = values[Math.round((i * last) / (width - 1))];
    if (value != null) out.push(value);
  }
  return out;
}

function chart(values: number[]): PaneBlock | null {
  if (values.length < 2) return null;
  const sampled = sample(values, CHART_WIDTH);
  const lo = Math.min(...sampled);
  const hi = Math.max(...sampled);
  const span = hi - lo;
  const text = sampled
    .map((n) => {
      if (span === 0) return BARS[3] ?? BARS[0];
      const index = Math.round(((n - lo) / span) * (BARS.length - 1));
      return BARS[Math.min(BARS.length - 1, Math.max(0, index))] ?? BARS[0];
    })
    .join("");
  return text.length > 0 ? { kind: "chart", text } : null;
}

/** One numeric NAV per point. A null NAV is not replaced with the index. */
function navValues(points: unknown[]): number[] {
  const values: number[] = [];
  for (const item of points) {
    if (typeof item === "number" && Number.isFinite(item)) {
      values.push(item);
      continue;
    }
    const nav = finite(rec(item)?.nav);
    if (nav != null) values.push(nav);
  }
  return values;
}

function paintPerformance(data: Record<string, unknown>): PaneBody {
  const metrics = rec(data.metrics);
  const nav = rec(data.nav);
  const benchmark = rec(data.benchmark);
  const head = stat([
    ["day", cell(metrics?.day_return_pct)],
    ["since", cell(metrics?.since_inception_pct)],
    ["excess", cell(metrics?.excess_return_pct)],
    ["alpha", cell(metrics?.alpha_pct)],
    ["IR", cell(metrics?.information_ratio)],
    ["beta", cell(metrics?.beta)],
    ["overlap", cell(metrics?.overlap_days)],
    ["NAV", cell(nav?.base100_tip)],
    ["date", cell(nav?.tip_date)],
    ["benchmark", cell(benchmark?.ticker)],
  ]);
  return head ? { blocks: [head] } : sentence(EMPTY_READ);
}

function pointRows(points: unknown[]): string[][] {
  const rows: string[][] = [];
  for (const item of points) {
    const row = rec(item);
    if (!row) continue;
    rows.push([cell(row.date), cell(row.nav), cell(row.day_return_pct), cell(row.contract), cell(row.index)]);
  }
  return rows;
}

function paintNav(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.points) || data.points.length === 0) return sentence(EMPTY_READ);
  const blocks: PaneBlock[] = [];
  const series = chart(navValues(data.points));
  if (series) blocks.push(series);
  const list = table(["date", "nav", "day", "contract", "index"], pointRows(data.points));
  if (list) blocks.push(list);
  return bodyOf(blocks);
}

function benchmarkRows(series: unknown): string[][] {
  const book = rec(series);
  if (!book) return [];
  const rows: string[][] = [];
  for (const [ticker, value] of Object.entries(book)) {
    if (!ticker || !Array.isArray(value)) continue;
    for (const item of value) {
      const row = rec(item);
      const date = named(row?.date);
      if (!row || !date) continue;
      rows.push([ticker, date, cell(row.close)]);
    }
  }
  return rows;
}

function paintBenchmarks(data: Record<string, unknown>): PaneBody {
  const list = table(["ticker", "date", "close"], benchmarkRows(data.series));
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

/** One tearsheet pane. Errors, stubs, and an empty read stay the official sentence. */
export function tearsheetBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub" || result.status === "empty" || data == null) {
    return textBody(result);
  }
  const row = rec(data);
  if (!row) return textBody(result);
  if (id === "performance") return withProvenance(result, paintPerformance(row));
  if (id === "navtable") return withProvenance(result, paintNav(row));
  if (id === "benchmarks") return withProvenance(result, paintBenchmarks(row));
  return textBody(result);
}
