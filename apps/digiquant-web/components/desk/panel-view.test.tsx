import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CHART_TYPES } from "../../../../clients/digiquant-tui/src/pages/panel-shape";
import { PanelChart } from "./panel-chart";
import { PanelView } from "./panel-view";
import { DeskPane } from "./pages/pane";

const nav = {
  points: [
    { date: "2026-10-08", nav: 204.04, index: 100 },
    { date: "2026-10-09", nav: 205.1, index: 100.52 },
  ],
};
const book = {
  rows: [
    { ticker: "UUP", weight_pct: 29.97 },
    { ticker: "DBO", weight_pct: 4.72 },
  ],
};
const noop = () => {};

describe("PanelView", () => {
  it("draws a chart-first block as a chart, with the toggle and the chart-type picker", () => {
    const html = renderToStaticMarkup(
      <PanelView id="nav" title="NAV · series" data={nav}>
        <p>table body</p>
      </PanelView>,
    );
    expect(html).toContain('data-mode="chart"');
    expect(html).toContain('data-chart="line"');
    expect(html).toContain('aria-label="Chart type"');
    expect(html).toMatch(/aria-pressed="true"[^>]*>Chart</);
    expect(html).not.toContain("table body");
    expect(html).not.toContain("204.04");
  });

  it("opens a table-first block on its table, with the toggle and no picker", () => {
    const html = renderToStaticMarkup(
      <PanelView id="book" title="Book · allocation" data={book}>
        <p>table body</p>
      </PanelView>,
    );
    expect(html).toContain('data-mode="table"');
    expect(html).toContain("table body");
    expect(html).toContain('aria-label="View"');
    expect(html).not.toContain('aria-label="Chart type"');
    expect(html).not.toContain("<svg");
  });

  it("leaves an unmapped block, or one with too few points, as its table with no controls", () => {
    for (const [id, data] of [
      ["ledger", book],
      ["nav", { points: [{ date: "2026-10-09", index: 100 }] }],
      ["nav", null],
    ] as const) {
      const html = renderToStaticMarkup(
        <PanelView id={id} title="t" data={data}>
          <p>table body</p>
        </PanelView>,
      );
      expect(html).toBe("<p>table body</p>");
    }
  });

  it("mounts every chart type a shape allows on the engine that draws it", () => {
    const series = [
      { label: "2026-08-31", value: 100 },
      { label: "2026-09-30", value: 101 },
    ];
    const names = [
      { label: "UUP", value: 29.97 },
      { label: "DBO", value: 4.72 },
      { label: "XLV", value: -1.5 },
    ];
    for (const shape of Object.keys(CHART_TYPES) as (keyof typeof CHART_TYPES)[]) {
      for (const type of CHART_TYPES[shape]) {
        const points = shape === "series" ? series : names.filter((point) => type === "bar" || point.value > 0);
        const html = renderToStaticMarkup(<PanelChart shape={shape} type={type} points={points} unit="index" label="x" />);
        const engine = shape === "series" && (type === "line" || type === "area") ? "vela" : "echarts";
        expect(html, `${shape}/${type}`).toContain(`data-chart="${type}"`);
        expect(html, `${shape}/${type}`).toContain(`data-engine="${engine}"`);
      }
    }
  });

  it("puts the toggle in a desk pane only when the page passes the read's data", () => {
    const pane = (panel?: { id: string; data: unknown }) =>
      renderToStaticMarkup(
        <DeskPane title="NAV · series" route="/nav-series" asOf={null} lines={["2026-10-09  100.52"]} tone="" focused={false} onFocus={noop} onNext={noop} panel={panel} />,
      );
    expect(pane()).not.toContain('role="toolbar"');
    expect(pane({ id: "nav", data: nav })).toContain('role="toolbar"');
  });
});
