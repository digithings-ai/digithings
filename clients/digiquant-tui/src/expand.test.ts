import { describe, expect, it } from "bun:test";
import { PAGE_LAYOUTS } from "./catalog";
import { expandLayout } from "./expand";
import { COLS, ROWS, type Layout } from "./grid";

const area = (layout: Layout) => layout.reduce((sum, p) => sum + p.w * p.h, 0);

describe("open a block in place", () => {
  it("grows the open block from its top-left and keeps every block on the grid", () => {
    for (const [path, layout] of Object.entries(PAGE_LAYOUTS)) {
      if (layout.length < 2) continue;
      for (const block of layout) {
        const next = expandLayout(layout, block.id);
        const open = next.find((p) => p.id === block.id)!;
        expect(next.map((p) => p.id), `${path} ${block.id}`).toEqual(layout.map((p) => p.id));
        expect(open.w * open.h, `${path} ${block.id}`).toBeGreaterThan(block.w * block.h);
        expect(area(next), `${path} ${block.id}`).toBe(COLS * ROWS);
        for (const p of next) {
          expect(p.w, `${path} ${block.id} ${p.id}`).toBeGreaterThanOrEqual(1);
          expect(p.h, `${path} ${block.id} ${p.id}`).toBeGreaterThanOrEqual(1);
        }
      }
    }
  });

  it("keeps the brief block's top-left and leaves no block covered", () => {
    const layout = PAGE_LAYOUTS["/brief"]!;
    const next = expandLayout(layout, "decision");
    const open = next.find((p) => p.id === "decision")!;
    expect([open.x, open.y]).toEqual([1, 4]);
    expect(open.w).toBeGreaterThan(4);
    expect(open.h).toBeGreaterThan(4);
  });

  it("returns the rest layout for no block or an unknown one", () => {
    const layout = PAGE_LAYOUTS["/brief"]!;
    expect(expandLayout(layout, null)).toBe(layout);
    expect(expandLayout(layout, "nope")).toBe(layout);
  });

  it("asks for more cells when the content needs them", () => {
    const layout = PAGE_LAYOUTS["/brief"]!;
    const open = expandLayout(layout, "signals", { w: 10, h: 8 }).find((p) => p.id === "signals")!;
    expect(open.w).toBeGreaterThanOrEqual(8);
  });
});
