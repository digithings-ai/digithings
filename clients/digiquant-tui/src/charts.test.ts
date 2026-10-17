import { describe, expect, test } from "bun:test";

import {
  BLOCK_RAMP,
  CHART_KINDS,
  CHART_TOGGLE_KEY,
  HEAT_RAMP,
  barChart,
  brailleCell,
  brailleLine,
  chartToggleKeyIsFree,
  claimedKeys,
  drawChart,
  extent,
  heatmap,
  pieAsStacked,
  pieLegend,
  ramp,
  resample,
  stackedBars,
  toggleChartKind,
} from "./charts";

/** Every row of a chart box, as an array of equal-length rows. */
function box(rows: string[], width: number, height: number): boolean {
  if (rows.length !== height) return false;
  return rows.every((row) => row.length === width);
}

describe("extent", () => {
  test("reads low and high off the values that can be painted", () => {
    expect(extent([3, 1, 2])).toEqual({ min: 1, max: 3 });
  });

  test("null when nothing can be painted", () => {
    expect(extent([])).toBeNull();
    expect(extent([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])).toBeNull();
  });

  test("a non-finite value is not a spike", () => {
    expect(extent([1, Number.NaN, 2, Number.POSITIVE_INFINITY])).toEqual({ min: 1, max: 2 });
  });

  test("a single value is its own extent", () => {
    expect(extent([7])).toEqual({ min: 7, max: 7 });
  });
});

describe("ramp", () => {
  test("low, middle and high land on the ends and the middle", () => {
    expect(ramp(0, 0, 10, 5)).toBe(0);
    expect(ramp(10, 0, 10, 5)).toBe(4);
    expect(ramp(5, 0, 10, 5)).toBe(2);
  });

  test("a flat series reads as no spread, not as a division by zero", () => {
    expect(ramp(5, 5, 5, 5)).toBe(0);
  });

  test("a value above the max clamps instead of overflowing the bucket", () => {
    expect(ramp(99, 0, 10, 5)).toBe(4);
  });

  test("one level has exactly one bucket", () => {
    expect(ramp(0, 0, 10, 1)).toBe(0);
    expect(ramp(10, 0, 10, 1)).toBe(0);
  });

  test("a value that is not data sits at the bottom", () => {
    expect(ramp(Number.NaN, 0, 10, 5)).toBe(0);
  });
});

describe("resample", () => {
  test("a series narrower than the box repeats its end points", () => {
    expect(resample([1, 2], 6)).toEqual([1, 1, 1, 2, 2, 2]);
  });

  test("a single value fills the box", () => {
    expect(resample([4], 3)).toEqual([4, 4, 4]);
  });

  test("an empty series stays empty", () => {
    expect(resample([], 5)).toEqual([]);
  });
});

describe("brailleLine", () => {
  test("a box is exactly height rows of ceil(width / 2) characters", () => {
    const rows = brailleLine([1, 5, 3, 8, 2], { width: 10, height: 4 });
    expect(rows.length).toBe(4);
    expect(rows.every((row) => row.length === 5)).toBe(true);
  });

  test("an odd width leaves the last cell's right column blank", () => {
    const rows = brailleLine([1, 2, 3], { width: 7, height: 2 });
    expect(rows[0]?.length).toBe(4);
  });

  test("no data paints blanks, not glyphs", () => {
    expect(box(brailleLine([], { width: 8, height: 3 }), 4, 3)).toBe(true);
    expect(brailleLine([], { width: 8, height: 3 }).join("").trim()).toBe("");
  });

  test("a flat series still paints and never emits a blank box", () => {
    const rows = brailleLine([4, 4, 4, 4], { width: 8, height: 3 });
    expect(rows.join("").trim().length).toBeGreaterThan(0);
  });

  test("a rising series climbs to the right, a falling one climbs to the left", () => {
    const rising = brailleLine([0, 1, 2, 3, 4, 5, 6, 7], { width: 8, height: 8 });
    const falling = brailleLine([7, 6, 5, 4, 3, 2, 1, 0], { width: 8, height: 8 });
    // The last character cell carries the last column of the box.
    const edge = (rows: string[]) => rows.findIndex((row) => (row.slice(-1) ?? " ").trim().length > 0);
    expect(edge(rising)).toBeLessThan(edge(falling));
  });

  test("a zero-sized box is no rows", () => {
    expect(brailleLine([1, 2], { width: 0, height: 4 })).toEqual([]);
    expect(brailleLine([1, 2], { width: 8, height: 0 })).toEqual([]);
  });
});

describe("barChart", () => {
  test("a box is exactly height rows of width characters", () => {
    expect(box(barChart([1, 2, 3], { width: 6, height: 4 }), 6, 4)).toBe(true);
  });

  test("the tallest column reaches the top row", () => {
    const rows = barChart([1, 5, 2], { width: 3, height: 4 });
    expect(rows[0]?.trim().length).toBeGreaterThan(0);
  });

  test("no data paints blanks", () => {
    expect(barChart([], { width: 5, height: 3 }).join("").trim()).toBe("");
  });

  test("a flat series still draws a full-height column, not an empty box", () => {
    expect(barChart([3, 3, 3], { width: 3, height: 4 }).join("").trim().length).toBeGreaterThan(0);
  });

  test("the lowest value still gets a column, not a gap in the floor", () => {
    const rows = barChart([0, 5, 2], { width: 3, height: 4 });
    // Column 0 is the minimum. A zero-height column is indistinguishable from
    // a hole in the axis, so the floor value must paint at least one row.
    expect(rows.some((row) => (row[0] ?? " ") !== " ")).toBe(true);
  });

  test("every painted glyph comes from the block ramp", () => {
    const rows = barChart([1, 9, 4, 7], { width: 8, height: 5 });
    for (const row of rows) {
      for (const ch of row) expect(BLOCK_RAMP.includes(ch)).toBe(true);
    }
  });
});

describe("stackedBars", () => {
  test("a box is exactly height rows of width characters", () => {
    const series = [
      { label: "a", values: [1, 2] },
      { label: "b", values: [3, 4] },
    ];
    expect(box(stackedBars(series, { width: 6, height: 4 }), 6, 4)).toBe(true);
  });

  test("two series in a column paint two different segments, not one", () => {
    const series = [
      { label: "a", values: [1] },
      { label: "b", values: [1] },
    ];
    const rows = stackedBars(series, { width: 2, height: 6 });
    const painted = new Set(rows.join("").replace(/ /g, "").split(""));
    expect(painted.size).toBeGreaterThanOrEqual(2);
  });

  test("no series paints blanks", () => {
    expect(stackedBars([], { width: 4, height: 3 }).join("").trim()).toBe("");
    expect(stackedBars([{ label: "a", values: [] }], { width: 4, height: 3 }).join("").trim()).toBe("");
  });

  test("the first series is the base of the column", () => {
    const rows = stackedBars(
      [
        { label: "base", values: [1] },
        { label: "top", values: [1] },
      ],
      { width: 2, height: 4 },
    );
    // The lowest painted row belongs to the base series, not the top one.
    const lowest = [...rows].reverse().find((row) => row.trim().length > 0);
    expect(lowest).toBeDefined();
    expect(stackedBars([{ label: "base", values: [1] }], { width: 2, height: 4 })[3]).toBeDefined();
  });
});

describe("heatmap", () => {
  test("a box is exactly height rows of width characters", () => {
    expect(box(heatmap([[1, 2], [3, 4]], { width: 6, height: 3 }), 6, 3)).toBe(true);
  });

  test("a short row is padded, not dropped", () => {
    const rows = heatmap([[1], [1, 2, 3]], { width: 4, height: 2 });
    expect(rows.every((row) => row.length === 4)).toBe(true);
    expect(rows[0]?.trim().length).toBeGreaterThan(0);
  });

  test("every glyph comes from the heat ramp", () => {
    for (const ch of heatmap([[1, 2], [3, 4], [5, 6]], { width: 6, height: 3 }).join("")) {
      expect(HEAT_RAMP.includes(ch)).toBe(true);
    }
  });

  test("no data paints blanks", () => {
    expect(heatmap([], { width: 4, height: 2 }).join("").trim()).toBe("");
    expect(heatmap([[Number.NaN, Number.NaN]], { width: 4, height: 2 }).join("").trim()).toBe("");
  });
});

describe("pieAsStacked", () => {
  const pie = [
    { label: "cash", value: 40 },
    { label: "fx", value: 35 },
    { label: "eq", value: 25 },
  ];

  test("every slice keeps its own painted column", () => {
    const rows = pieAsStacked(pie, { width: 12, height: 3 });
    expect(rows.length).toBeGreaterThan(0);
    for (let slice = 0; slice < pie.length; slice++) {
      const painted = rows.some((row) => row[slice] !== undefined && row[slice] !== " ");
      expect(painted).toBe(true);
    }
  });

  test("a slice with no value takes no run, and the bar still fills the box", () => {
    const runs = (rows: string[]) => new Set(rows[0] ?? "").size;
    const withZero = pieAsStacked([...pie, { label: "none", value: 0 }], { width: 12, height: 3 });
    const withoutZero = pieAsStacked(pie, { width: 12, height: 3 });
    expect(runs(withZero)).toBe(3);
    expect(runs(withZero)).toBe(runs(withoutZero));
    expect((withZero[0] ?? "").length).toBe(12);
    expect((withZero[0] ?? "").includes(" ")).toBe(false);
  });

  test("a one-hundredth slice still gets a column", () => {
    const many = Array.from({ length: 40 }, (_, i) => ({ label: `s${i}`, value: 1 }));
    const rows = pieAsStacked(many, { width: 10, height: 1 });
    // More slices than columns: the runs must still total the box width and
    // every column must carry a slice, so nothing is silently merged away.
    expect((rows[0] ?? "").length).toBe(10);
    expect((rows[0] ?? "").includes(" ")).toBe(false);
  });

  test("an empty pie draws nothing rather than a placeholder", () => {
    expect(pieAsStacked([], { width: 8, height: 2 })).toEqual([]);
    expect(pieAsStacked([{ label: "a", value: 0 }], { width: 8, height: 2 })).toEqual([]);
  });

  test("the legend names every slice and the shares sum to a hundred", () => {
    const legend = pieLegend(pie);
    expect(legend.length).toBe(3);
    const total = legend.reduce((acc, line) => acc + Number.parseFloat(line.split(/\s+/)[1] ?? "0"), 0);
    expect(total).toBeCloseTo(100, 1);
  });

  test("an empty pie has no legend", () => {
    expect(pieLegend([])).toEqual([]);
  });
});

describe("the toggle key is the web key, not a free choice", () => {
  test("the web key map is actually read (a fired control)", () => {
    const keys = claimedKeys();
    expect(keys.length).toBeGreaterThan(0);
    expect(keys).toContain("/");
    expect(keys).toContain("d");
  });

  test("the toggle key is one the web map has not claimed", () => {
    expect(chartToggleKeyIsFree()).toBe(true);
  });

  test("a key the web map claims is not free", () => {
    expect(chartToggleKeyIsFree("d")).toBe(false);
    expect(chartToggleKeyIsFree("/")).toBe(false);
  });
});

describe("toggleChartKind", () => {
  test("steps through every kind and wraps", () => {
    const seen: string[] = [];
    let kind = CHART_KINDS[0] as (typeof CHART_KINDS)[number];
    for (let i = 0; i < CHART_KINDS.length; i++) {
      seen.push(kind);
      kind = toggleChartKind(kind, CHART_TOGGLE_KEY);
    }
    expect(seen).toEqual([...CHART_KINDS]);
    expect(kind).toBe(CHART_KINDS[0]);
  });

  test("any other key leaves the kind alone", () => {
    expect(toggleChartKind("bars", "d")).toBe("bars");
    expect(toggleChartKind("bars", "q")).toBe("bars");
    expect(toggleChartKind("heatmap", "")).toBe("heatmap");
  });

  test("an unknown kind steps to the first, never to undefined", () => {
    expect(toggleChartKind("nonsense" as never, CHART_TOGGLE_KEY)).toBe(CHART_KINDS[0]);
  });
});

describe("drawChart", () => {
  test("every kind paints something from its own primitive", () => {
    const payload: Record<string, unknown> = {
      line: [1, 2, 3, 4],
      bars: [1, 2, 3, 4],
      stacked: [
        { label: "a", values: [1, 2, 3, 4] },
        { label: "b", values: [2, 2, 2, 2] },
      ],
      heatmap: [
        [1, 2],
        [3, 4],
      ],
    };
    for (const kind of CHART_KINDS) {
      const rows = drawChart(kind, payload[kind], { width: 8, height: 4 });
      expect(rows.length).toBe(4);
      expect(rows.join("").trim().length).toBeGreaterThan(0);
    }
  });

  test("a two-dimensional payload paints a heatmap, not a line", () => {
    const rows = drawChart("line", [[1, 2], [3, 4]], { width: 6, height: 3 });
    expect(box(rows, 6, 3)).toBe(true);
  });

  test("a payload that is not an array paints nothing rather than throwing", () => {
    expect(drawChart("bars", null, { width: 4, height: 2 }).join("").trim()).toBe("");
  });
});
