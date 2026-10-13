/** How a desk table column behaves on a narrow screen.
 *  key: the row label, pinned left while the rest scrolls.
 *  num: a number or a date, never wrapped, right-aligned.
 *  text: prose, the column that gives up width and wraps on word breaks. */
export type ColumnRole = "key" | "num" | "text";

const EMPTY = new Set(["", "—", "–", "-", "n/a", "N/A"]);
const NUMBER = /^[+\-−]?[$€£¥]?\d[\d,]*(\.\d+)?\s?(%|bp|bps|x|k|m|bn|[A-Z]{3})?$/i;
const DATE = /^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?Z?)?$/;

function isNumeric(cell: string): boolean {
  return NUMBER.test(cell) || DATE.test(cell);
}

/** One role per column. A column is `num` only when every filled cell reads as a number or date. */
export function columnRoles(columns: string[], rows: string[][]): ColumnRole[] {
  const width = Math.max(columns.length, ...rows.map((row) => row.length), 0);
  const roles: ColumnRole[] = [];
  for (let col = 0; col < width; col += 1) {
    if (col === 0 && width > 1) {
      roles.push("key");
      continue;
    }
    const filled = rows.map((row) => (row[col] ?? "").trim()).filter((cell) => !EMPTY.has(cell));
    roles.push(filled.length > 0 && filled.every(isNumeric) ? "num" : "text");
  }
  return roles;
}
