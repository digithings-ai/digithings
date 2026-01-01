import { describe, expect, it } from "bun:test";
import { bodySize, compactBody, fitColumns, hiddenLabel } from "./pane-fit";

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

  it("keeps the start of long prose and marks the cut", () => {
    const text = "The book is long duration into the meeting. ".repeat(6).trim();
    const { body } = compactBody({ blocks: [{ kind: "sentence", text }] }, { chars: 20, rows: 2 });
    const face = body.blocks[0];
    expect(face?.kind).toBe("sentence");
    if (face?.kind !== "sentence") return;
    expect(face.text.length).toBeLessThanOrEqual(40);
    expect(face.text.endsWith("…")).toBe(true);
  });

  it("measures what an open card needs", () => {
    expect(bodySize({ blocks: [{ kind: "table", columns, rows }] })).toEqual({ chars: 6 * 3 + 9 + 10 + 6 + 10 + 6 + 6, lines: 13 });
    expect(bodySize({ blocks: [{ kind: "sentence", text: "x".repeat(150) }] })).toEqual({ chars: 72, lines: 3 });
  });
});
