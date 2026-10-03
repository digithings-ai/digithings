import { DASH, EMPTY_READ, type ReadResult } from "../read";
import { shapeLines, type PaneBlock, type PaneBody } from "./shape";

/** Theses is two panes: counts plus the thesis table, then the signals table. */

const COUNT_KEYS = ["active", "watch", "exited"] as const;
const THESIS_COLUMNS = ["id", "thesis", "state", "vehicles", "evidence", "kill"];
const SIGNAL_COLUMNS = ["id", "thesis", "state", "note"];

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

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function vehicles(value: unknown): string {
  if (!Array.isArray(value)) return DASH;
  const names = value.filter((item): item is string => typeof item === "string" && item.length > 0);
  return names.length > 0 ? names.join(" ") : DASH;
}

function countStat(value: unknown): PaneBlock | null {
  const row = rec(value);
  if (!row) return null;
  const pairs: [string, string][] = [];
  for (const key of COUNT_KEYS) {
    const count = finite(row[key]);
    if (count == null) continue;
    pairs.push([key, JSON.stringify(count)]);
  }
  return stat(pairs);
}

function thesisRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const id = named(row?.id);
    if (!row || !id) continue;
    rows.push([id, cell(row.name), cell(row.state), vehicles(row.vehicles), cell(row.evidence), cell(row.kill_condition)]);
  }
  return rows;
}

function signalRows(value: unknown): string[][] {
  if (!Array.isArray(value)) return [];
  const rows: string[][] = [];
  for (const item of value) {
    const row = rec(item);
    const id = named(row?.id);
    if (!row || !id) continue;
    rows.push([id, cell(row.name), cell(row.state), cell(row.note)]);
  }
  return rows;
}

function paintTheses(data: Record<string, unknown>): PaneBody {
  const list = table(THESIS_COLUMNS, thesisRows(data.theses));
  if (!list) return sentence(EMPTY_READ);
  const blocks: PaneBlock[] = [];
  const head = countStat(data.counts);
  if (head) blocks.push(head);
  blocks.push(list);
  return { blocks };
}

function paintSignals(data: Record<string, unknown>): PaneBody {
  const list = table(SIGNAL_COLUMNS, signalRows(data.theses));
  return list ? { blocks: [list] } : sentence(EMPTY_READ);
}

/** One theses pane. Errors, stubs, and an empty list stay the official sentence. */
export function thesesBody(id: string, data: unknown, result: ReadResult): PaneBody {
  if (result.status === "error" || result.status === "stub" || result.status === "empty" || data == null) {
    return textBody(result);
  }
  const row = rec(data);
  if (!row) return textBody(result);
  if (id === "theses") return withProvenance(result, paintTheses(row));
  if (id === "signals") return withProvenance(result, paintSignals(row));
  return textBody(result);
}
