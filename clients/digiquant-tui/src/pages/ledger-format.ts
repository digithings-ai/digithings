import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Ledger is two panes: position events, then cash. Each empty list stays the empty sentence. */

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

function named(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function eventRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const date = named(row?.date);
    const ticker = named(row?.ticker);
    if (!row || !date || !ticker) continue;
    rows.push([
      date,
      ticker,
      cell(row.type),
      cell(row.fill_price),
      cell(row.avg_entry),
      cell(row.realized_pct),
      cell(row.prev_weight_pct),
      cell(row.weight_pct),
    ]);
  }
  return rows;
}

function cashRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const date = named(row?.date);
    if (!row || !date) continue;
    rows.push([date, cell(row.kind), cell(row.amount), cell(row.balance)]);
  }
  return rows;
}

const EVENT_COLUMNS = ["date", "ticker", "type", "fill", "entry", "realized", "prev", "weight"];
const CASH_COLUMNS = ["date", "kind", "amount", "balance"];

function paintEvents(data: Record<string, unknown>): PaneBody {
  const list = table(EVENT_COLUMNS, eventRows(data.events));
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

function paintCash(data: Record<string, unknown>): PaneBody {
  const list = table(CASH_COLUMNS, cashRows(data.entries));
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

/** One ledger pane. Errors, stubs, and an empty list stay the official sentence. */
export function ledgerBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub" || result.status === "empty" || data == null) {
    return textBody(result);
  }
  const row = rec(data);
  if (!row) return textBody(result);
  if (id === "ledger") return withProvenance(result, paintEvents(row));
  if (id === "cash") return withProvenance(result, paintCash(row));
  return textBody(result);
}
