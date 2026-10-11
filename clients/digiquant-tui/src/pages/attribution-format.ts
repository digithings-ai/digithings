import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Attribution is two tables: sleeves, then names. Contribution is the payload's basis points. */

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

function sleeveRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    if (!row || typeof row.sleeve !== "string" || row.sleeve.length === 0) continue;
    rows.push([row.sleeve, cell(row.contribution_bp)]);
  }
  return rows;
}

function nameRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    if (!row || typeof row.ticker !== "string" || row.ticker.length === 0) continue;
    rows.push([row.ticker, cell(row.sleeve), cell(row.contribution_bp)]);
  }
  return rows;
}

function paintAttribution(data: Record<string, unknown>): PaneBody {
  const blocks: PaneBlock[] = [];
  const sleeves = table(["sleeve", "bp"], sleeveRows(data.sleeves));
  const names = table(["ticker", "sleeve", "bp"], nameRows(data.names));
  if (sleeves) blocks.push(sleeves);
  if (names) blocks.push(names);
  return blocks.length > 0 ? { blocks } : sentence(EMPTY_READ);
}

/** The attribution pane. Errors, stubs, and two empty lists stay the official sentence. */
export function attributionBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub" || result.status === "empty" || data == null) {
    return textBody(result);
  }
  const row = rec(data);
  if (id !== "attribution" || !row) return textBody(result);
  return withProvenance(result, paintAttribution(row));
}
