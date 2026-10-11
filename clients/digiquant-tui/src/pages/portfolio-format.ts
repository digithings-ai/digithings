import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Portfolio panes. A chart is one row of the numbers the payload already has. */
const PORTFOLIO_IDS = ["portfolio", "sleeves", "movers", "book", "nav", "drawdown"] as const;

type PortfolioId = (typeof PORTFOLIO_IDS)[number];

const BARS = "▁▂▃▄▅▆▇█";
const CHART_WIDTH = 24;

function isPortfolioId(id: string): id is PortfolioId {
  return (PORTFOLIO_IDS as readonly string[]).includes(id);
}

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

function chart(values: number[], minCount: number): PaneBlock | null {
  if (values.length < minCount) return null;
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

function paintPortfolio(data: Record<string, unknown>): PaneBody {
  const tip = rec(data.nav_tip);
  const invested = rec(data.invested);
  const head = stat([
    ["NAV", cell(tip?.nav)],
    ["date", cell(tip?.date)],
    ["contract", cell(tip?.contract)],
    ["invested", cell(invested?.envelope_pct)],
    ["cash", cell(invested?.cash_pct)],
  ]);
  return head ? { blocks: [head] } : sentence(EMPTY_READ);
}

function paintSleeves(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.sleeves) || data.sleeves.length === 0) return sentence(EMPTY_READ);
  const rows: string[][] = [];
  for (const item of data.sleeves) {
    const row = rec(item);
    if (!row || typeof row.sleeve !== "string" || row.sleeve.length === 0) continue;
    rows.push([row.sleeve, cell(row.names), cell(row.weight_pct)]);
  }
  const list = table(["sleeve", "names", "weight"], rows);
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function paintMovers(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.rows)) return sentence(EMPTY_READ);
  const rows: string[][] = [];
  for (const item of data.rows) {
    const row = rec(item);
    if (!row || typeof row.ticker !== "string" || row.ticker.length === 0) continue;
    rows.push([
      row.ticker,
      cell(row.sleeve),
      cell(row.scaled_weight_pct),
      cell(row.current_price),
      cell(row.day_return_pct),
      cell(row.unrealized_pct),
    ]);
  }
  const list = table(["ticker", "sleeve", "weight", "price", "day", "unrealized"], rows);
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function paintBook(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.rows)) return sentence(EMPTY_READ);
  const rows: string[][] = [];
  for (const item of data.rows) {
    const row = rec(item);
    if (!row || typeof row.ticker !== "string" || row.ticker.length === 0) continue;
    rows.push([
      row.ticker,
      cell(row.weight_pct),
      cell(row.scaled_weight_pct),
      cell(row.entry_price),
      cell(row.current_price),
      cell(row.unrealized_pct),
    ]);
  }
  const list = table(["ticker", "weight", "scaled", "entry", "price", "unrealized"], rows);
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
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
  const navs = data.points.map((item) => finite(rec(item)?.nav)).filter((n): n is number => n != null);
  const blocks: PaneBlock[] = [];
  const series = data.points.length >= 2 ? chart(navs, 2) : null;
  if (!series) blocks.push({ kind: "sentence", text: EMPTY_READ });
  if (series) blocks.push(series);
  const list = table(["date", "nav", "day", "contract", "index"], pointRows(data.points));
  if (list) blocks.push(list);
  return bodyOf(blocks);
}

function paintDrawdown(data: Record<string, unknown>): PaneBody {
  const blocks: PaneBlock[] = [];
  const head = stat([
    ["max", cell(data.max_pct)],
    ["current", cell(data.current_pct)],
  ]);
  if (head) blocks.push(head);
  const series = Array.isArray(data.series) ? data.series : [];
  const values = series.map((item) => finite(rec(item)?.v)).filter((n): n is number => n != null);
  const line = chart(values, 1);
  if (line) blocks.push(line);
  return bodyOf(blocks);
}

function paint(id: PortfolioId, data: Record<string, unknown>): PaneBody {
  switch (id) {
    case "portfolio":
      return paintPortfolio(data);
    case "sleeves":
      return paintSleeves(data);
    case "movers":
      return paintMovers(data);
    case "book":
      return paintBook(data);
    case "nav":
      return paintNav(data);
    case "drawdown":
      return paintDrawdown(data);
    default: {
      const exhaustive: never = id;
      return sentence(String(exhaustive));
    }
  }
}

/** One portfolio pane. Errors, stubs, and empty payloads stay the official sentence. */
export function portfolioBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub" || result.status === "empty" || data == null) {
    return textBody(result);
  }
  const row = rec(data);
  if (!row || !isPortfolioId(id)) return textBody(result);
  return withProvenance(result, paint(id, row));
}
