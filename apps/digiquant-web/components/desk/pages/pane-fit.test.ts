import { describe, expect, it } from "vitest";
import { compactBody, fitColumns, hiddenLabel } from "./pane-fit";

describe("desk card face", () => {
  const columns = ["Direction", "Entry date", "Entry", "Exit date", "Exit", "Return"];
  const rows = Array.from({ length: 12 }, (_, i) => ["long", "2026-10-01", "101.20", "2026-10-09", "104.80", `+${i}.0%`]);

  it("keeps the leading columns that fit and always the first", () => {
    expect(fitColumns(columns, rows, 200)).toBe(6);
    expect(fitColumns(columns, rows, 27)).toBe(2);
    expect(fitColumns(columns, rows, 3)).toBe(1);
  });

  it("trims a table to the columns that fit and the first rows", () => {
    const { body, hidden } = compactBody({ blocks: [{ kind: "table", columns, rows }] }, { chars: 27, rows: 8 });
    const table = body.blocks[0];
    expect(table?.kind).toBe("table");
    if (table?.kind !== "table") return;
    expect(table.columns).toEqual(["Direction", "Entry date"]);
    expect(table.rows).toHaveLength(8);
    expect(table.rows.every((row) => row.length === 2)).toBe(true);
    expect(hidden).toEqual({ columns: 4, rows: 4, points: 0 });
    expect(hiddenLabel(hidden)).toBe("+4 cols · +4 rows");
  });

  it("keeps the recent end of a chart", () => {
    const { body, hidden } = compactBody({ blocks: [{ kind: "chart", text: "▁▂▃▄▅▆▇█" }] }, { chars: 3, rows: 8 });
    expect(body.blocks[0]).toEqual({ kind: "chart", text: "▆▇█" });
    expect(hiddenLabel(hidden)).toBe("+5 pts");
  });

  it("leaves a body that already fits untouched", () => {
    const blocks = [
      { kind: "sentence" as const, text: "The brief is not published yet." },
      { kind: "table" as const, columns: [], rows: [["NAV", "1.04"]] },
    ];
    const { body, hidden } = compactBody({ blocks }, { chars: 80, rows: 8 });
    expect(body.blocks).toEqual(blocks);
    expect(hiddenLabel(hidden)).toBeNull();
  });
});
