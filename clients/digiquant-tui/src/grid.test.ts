import { expect, test } from "bun:test";
import { BLOCKS, PAGE_LAYOUTS, PAGES, layoutMatchesPage } from "./catalog";
import { clampSize, fit, nudge, place } from "./grid";

test("fit clamps a placement into the grid", () => {
  expect(fit({ id: "a", x: 0, y: 0, w: 1, h: 99 })).toEqual({ id: "a", x: 1, y: 1, w: 2, h: 12 });
});

test("place pushes the overlapped block down", () => {
  const layout = [
    { id: "a", x: 1, y: 1, w: 4, h: 4 },
    { id: "b", x: 5, y: 1, w: 4, h: 4 },
  ];
  const next = place(layout, { id: "a", x: 5, y: 1, w: 4, h: 4 });
  expect(next?.find((p) => p.id === "b")?.y).toBe(5);
});

test("nudge moves a block and refuses a resize past the minimum", () => {
  const layout = [
    { id: "a", x: 1, y: 1, w: 4, h: 4 },
    { id: "b", x: 7, y: 1, w: 4, h: 4 },
  ];
  expect(nudge(layout, "a", 1, 0, false)?.find((p) => p.id === "a")).toMatchObject({ x: 2, y: 1 });
  expect(nudge(layout, "a", 1, 0, true)?.find((p) => p.id === "a")).toMatchObject({ w: 5, x: 1 });
  expect(nudge([{ id: "a", x: 1, y: 1, w: 2, h: 2 }], "a", -1, 0, true)).toBeNull();
});

test("a packed page trades slots when a push will not fit", () => {
  const layout = [
    { id: "a", x: 1, y: 1, w: 8, h: 3 },
    { id: "b", x: 9, y: 1, w: 4, h: 3 },
    { id: "c", x: 1, y: 4, w: 12, h: 9 },
  ];
  const next = nudge(layout, "a", 1, 0, false);
  expect(next?.find((p) => p.id === "a")).toMatchObject({ x: 9, y: 1, w: 4, h: 3 });
  expect(next?.find((p) => p.id === "b")).toMatchObject({ x: 1, y: 1, w: 8, h: 3 });
});

test("clampSize keeps the origin", () => {
  expect(clampSize({ id: "a", x: 11, y: 11, w: 4, h: 4 })).toEqual({ id: "a", x: 11, y: 11, w: 2, h: 2 });
});

test("every page block has one route, and web-only pages are absent", () => {
  const routes: string[] = [];
  for (const page of PAGES) {
    const layout = PAGE_LAYOUTS[page.path];
    expect(layout?.length).toBeGreaterThan(0);
    for (const placement of layout) {
      const block = BLOCKS[placement.id];
      expect(block?.route.startsWith("/")).toBe(true);
      routes.push(block.route);
    }
  }
  const joined = routes.join(" ");
  expect(joined.includes("/markets/")).toBe(false);
  expect(joined.includes("/charts/")).toBe(false);
  expect(joined.includes("/chat/")).toBe(false);
  expect(BLOCKS["pl-canvas"]?.kind).toBe("graph");
  expect(PAGES.some((p) => p.path === "/tools/chat")).toBe(false);
});

test("a page change does not keep the previous page's blocks", () => {
  const brief = PAGE_LAYOUTS["/brief"];
  expect(layoutMatchesPage("/brief", brief)).toBe(true);
  expect(layoutMatchesPage("/fx/ideas", brief)).toBe(false);
  const moved = brief.map((p, i) => (i === 0 ? { ...p, x: p.x + 1 } : p));
  expect(layoutMatchesPage("/brief", moved)).toBe(true);
});
