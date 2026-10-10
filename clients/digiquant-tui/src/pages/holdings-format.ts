import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Holdings is one table of the enriched book rows. No group headers and no total row. */

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

function table(columns: string[], rows: string[][]): PaneBlock | null {
  if (rows.length === 0) return null;
  return { kind: "table", columns, rows };
}

function sentence(text: string): PaneBody {
  return { blocks: [{ kind: "sentence", text }] };
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

function paintHoldings(data: Record<string, unknown>): PaneBody {
  if (!Array.isArray(data.rows) || data.rows.length === 0) return sentence(EMPTY_READ);
  const rows: string[][] = [];
  for (const item of data.rows) {
    const row = rec(item);
    if (!row || typeof row.ticker !== "string" || row.ticker.length === 0) continue;
    rows.push([
      row.ticker,
      cell(row.name),
      cell(row.sleeve),
      cell(row.scaled_weight_pct),
      cell(row.shares),
      cell(row.current_price),
      cell(row.value),
      cell(row.day_return_pct),
      cell(row.thesis_id),
    ]);
  }
  const list = table(
    ["ticker", "name", "sleeve", "weight", "shares", "price", "value", "day", "thesis"],
    rows,
  );
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

/** The holdings pane. Errors, stubs, and an empty book stay the official sentence. */
export function holdingsBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub" || result.status === "empty" || data == null) {
    return textBody(result);
  }
  const row = rec(data);
  if (id !== "holdings" || !row) return textBody(result);
  return withProvenance(result, paintHoldings(row));
}
