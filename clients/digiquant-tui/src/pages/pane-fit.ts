import type { PaneBlock, PaneBody } from "./shape";

/** Cell padding (`px-2`) both sides, in characters. */
const CELL_PAD = 3;
/** Rows a compact table keeps when the card height is not known. The open card shows the rest. */
export const COMPACT_ROWS = 8;

export type Fit = { chars: number; rows: number };

/** What the compact card left out, so its footer can say so. */
export type Hidden = { columns: number; rows: number; points: number };

function widthOf(columns: string[], rows: string[][]): number {
  return rows.reduce((max, row) => Math.max(max, row.length), columns.length);
}

/** Leading columns whose widest cell fits `chars`. The first column always stays. */
export function fitColumns(columns: string[], rows: string[][], chars: number): number {
  const count = widthOf(columns, rows);
  let used = 0;
  for (let i = 0; i < count; i += 1) {
    const widest = rows.reduce((max, row) => Math.max(max, (row[i] ?? "").length), (columns[i] ?? "").length);
    used += widest + CELL_PAD;
    if (used > chars) return Math.max(1, i);
  }
  return count;
}

/** The most recent `chars` points of each chart row. */
function tail(text: string, chars: number): { text: string; dropped: number } {
  let dropped = 0;
  const lines = text.split("\n").map((line) => {
    const points = Array.from(line);
    if (points.length <= chars) return line;
    dropped = Math.max(dropped, points.length - chars);
    return points.slice(points.length - chars).join("");
  });
  return { text: lines.join("\n"), dropped };
}

/** The first `rows` wrapped lines of a sentence, with an ellipsis when it goes on. */
function clampText(text: string, chars: number, rows: number): string {
  const out: string[] = [];
  for (const line of text.split("\n")) {
    const wrapped = Math.max(1, Math.ceil(Array.from(line).length / chars));
    const room = rows - out.length;
    if (room <= 0) break;
    if (wrapped <= room) {
      out.push(line);
      continue;
    }
    out.push(`${Array.from(line).slice(0, room * chars - 1).join("").trimEnd()}…`);
    return out.join("\n");
  }
  return out.length < text.split("\n").length ? `${out.join("\n")}…` : out.join("\n");
}

/** The card face: the columns that fit, the first rows, the recent end of each chart, the start of the prose. */
export function compactBody(body: PaneBody, fit: Fit): { body: PaneBody; hidden: Hidden } {
  const hidden: Hidden = { columns: 0, rows: 0, points: 0 };
  const chars = Math.max(1, Math.floor(fit.chars));
  const rows = Math.max(1, Math.floor(fit.rows));
  const blocks = body.blocks.map((block): PaneBlock => {
    if (block.kind === "sentence") return { kind: "sentence", text: clampText(block.text, chars, rows) };
    if (block.kind === "chart") {
      const cut = tail(block.text, chars);
      hidden.points = Math.max(hidden.points, cut.dropped);
      return { kind: "chart", text: cut.text };
    }
    if (block.kind !== "table") return block;
    const keep = fitColumns(block.columns, block.rows, chars);
    hidden.columns = Math.max(hidden.columns, widthOf(block.columns, block.rows) - keep);
    hidden.rows += Math.max(0, block.rows.length - rows);
    return {
      kind: "table",
      columns: block.columns.slice(0, keep),
      rows: block.rows.slice(0, rows).map((row) => row.slice(0, keep)),
    };
  });
  return { body: { blocks }, hidden };
}

/** `+2 cols · +14 rows · +40 pts`, or null when the card shows everything. */
export function hiddenLabel(hidden: Hidden): string | null {
  const parts: string[] = [];
  if (hidden.columns) parts.push(`+${hidden.columns} col${hidden.columns === 1 ? "" : "s"}`);
  if (hidden.rows) parts.push(`+${hidden.rows} row${hidden.rows === 1 ? "" : "s"}`);
  if (hidden.points) parts.push(`+${hidden.points} pts`);
  return parts.length ? parts.join(" · ") : null;
}

/** Characters across and lines down the whole body needs, so an open card can ask for that much room. */
export function bodySize(body: PaneBody, wrap = 72): { chars: number; lines: number } {
  let chars = 0;
  let lines = 0;
  for (const block of body.blocks) {
    if (block.kind === "table") {
      const count = widthOf(block.columns, block.rows);
      let across = 0;
      for (let i = 0; i < count; i += 1) {
        across += block.rows.reduce((max, row) => Math.max(max, (row[i] ?? "").length), (block.columns[i] ?? "").length) + CELL_PAD;
      }
      chars = Math.max(chars, across);
      lines += block.rows.length + (block.columns.length ? 1 : 0);
      continue;
    }
    for (const line of block.text.split("\n")) {
      const length = Array.from(line).length;
      if (block.kind === "sentence") {
        chars = Math.max(chars, Math.min(length, wrap));
        lines += Math.max(1, Math.ceil(length / wrap));
      } else {
        chars = Math.max(chars, length);
        lines += 1;
      }
    }
  }
  return { chars, lines };
}
