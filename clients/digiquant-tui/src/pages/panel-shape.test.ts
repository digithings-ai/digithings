import { expect, test } from "bun:test";
import { BLOCKS } from "../catalog";
import { CHART_TYPES, PANEL_SHAPES, chartFor, panelData } from "./panel-shape";

test("every mapped block is a catalog block, and its first chart fits its shape", () => {
  for (const [id, spec] of Object.entries(PANEL_SHAPES)) {
    expect(BLOCKS[id]).toBeDefined();
    expect(CHART_TYPES[spec.shape]).toContain(spec.chart);
  }
});

test("an unmapped block, a missing row array and a single point stay a table", () => {
  expect(panelData("ledger", { rows: [{ ticker: "A", weight_pct: 1 }] })).toBeNull();
  expect(panelData("nav", { tip: null })).toBeNull();
  expect(panelData("nav", null)).toBeNull();
  expect(panelData("nav", { points: [{ date: "2026-10-09", index: 101 }] })).toBeNull();
});

test("nav plots the chained index, not raw nav, in date order", () => {
  const panel = panelData("nav", {
    points: [
      { date: "2026-10-08", nav: 204.04, index: 100 },
      { date: "2026-10-09", nav: 205.1, index: 100.52 },
    ],
  });
  expect(panel?.points).toEqual([
    { label: "2026-10-08", value: 100 },
    { label: "2026-10-09", value: 100.52 },
  ]);
  expect(panel?.spec.mode).toBe("chart");
  expect(panel?.charts).toEqual(["line", "area", "bar"]);
});

test("a null value is dropped, never drawn as zero, and cash is not a slice", () => {
  const panel = panelData("book", {
    rows: [
      { ticker: "UUP", weight_pct: 29.97 },
      { ticker: "XLV", weight_pct: null },
      { ticker: "CASH", weight_pct: 40, is_cash: true },
      { ticker: "DBO", weight_pct: 4.72 },
    ],
  });
  expect(panel?.points).toEqual([
    { label: "UUP", value: 29.97 },
    { label: "DBO", value: 4.72 },
  ]);
  expect(panel?.spec.mode).toBe("table");
});

test("a negative value removes donut and treemap; ranking sorts high to low", () => {
  const signed = panelData("sleeves", {
    sleeves: [
      { sleeve: "Rates", weight_pct: 12 },
      { sleeve: "Short", weight_pct: -3 },
    ],
  });
  expect(signed?.charts).toEqual(["bar"]);
  expect(chartFor(signed!, "donut")).toBe("bar");

  const ranked = panelData("attribution", {
    names: [
      { ticker: "A", contribution_bp: -4 },
      { ticker: "B", contribution_bp: 9 },
      { ticker: "C", contribution_bp: 1 },
    ],
  });
  expect(ranked?.points.map((point) => point.label)).toEqual(["B", "C", "A"]);
});

test("a saved chart pick wins only when the shape allows it", () => {
  const panel = panelData("drawdown", { series: [{ t: "2026-10-08", v: 0 }, { t: "2026-10-09", v: -1.2 }] })!;
  expect(chartFor(panel, null)).toBe("area");
  expect(chartFor(panel, "line")).toBe("line");
  expect(chartFor(panel, "donut")).toBe("area");
});
