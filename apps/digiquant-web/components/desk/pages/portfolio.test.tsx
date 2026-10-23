import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { STUB_READ, type ReadResult } from "digiquant-tui/read";
import type { OfficialRead } from "../read-block";
import { TearsheetPanes } from "./portfolio";

const OK: ReadResult = { status: "ok", lines: [], asOf: "2026-09-24" };

const NAV = {
  plot: {
    series: "index",
    accounting_nav: { contract: "legacy_estimate", plottable: false, reason: "all_legacy_estimate" },
  },
  tip: { date: "2026-09-24", contract: "legacy_estimate" },
  points: [
    { index: 100, date: "2026-09-22", nav: 100, day_return_pct: null, contract: "finalized_accounting" },
    { index: 100.5, date: "2026-09-23", nav: 100.5, day_return_pct: 0.5, contract: "finalized_accounting" },
    { index: 101.25, date: "2026-09-24", nav: 101.25, day_return_pct: 0.746, contract: "finalized_accounting" },
  ],
};

const BENCHMARKS = {
  universe: ["SPY", "QQQ"],
  series: {
    SPY: [
      { date: "2026-09-23", close: 512.3 },
      { date: "2026-09-24", close: 514.1 },
    ],
    QQQ: [{ date: "2026-09-24", close: 448.75 }],
  },
  aligned_start: "2025-09-24",
  overlap_days: 21,
  reason: null,
};

const read = (result: ReadResult, data: unknown = null): OfficialRead => ({ result, data });

const render = (reads: Record<string, OfficialRead> = {}) =>
  renderToStaticMarkup(<TearsheetPanes reads={reads} />);

describe("tearsheet NAV block", () => {
  it("paints the index series with its summary and the table/chart toggle", () => {
    const html = render({ navtable: read(OK, NAV) });
    expect(html).toContain('data-route="/nav-series"');
    expect(html).toContain("NAV · by date");
    // Summary figures, read off the payload.
    expect(html).toContain("Tip");
    expect(html).toContain("2026-09-24");
    expect(html).toContain("Points");
    expect(html).toContain("101.25");
    expect(html).toContain("+0.75%");
    // The accounting NAV is named, never plotted.
    expect(html).toContain("legacy_estimate");
    expect(html).toContain("not plottable");
    expect(html).toContain("all_legacy_estimate");
    // The series itself, as a sparkline and as rows.
    expect(html).toContain("<svg");
    expect(html).toContain("NAV index over 3 points");
    expect(html).toContain("2026-09-22");
    expect(html).toContain("100.00");
    // The pane keeps its PanelView toggle.
    expect(html).toContain("Table");
    expect(html).toContain("Chart");
  });

  it("draws no sparkline when the read carries a single level", () => {
    const html = render({ navtable: read(OK, { ...NAV, points: [NAV.points[0]] }) });
    expect(html).not.toContain("<svg");
    expect(html).toContain("2026-09-22");
  });

  it("says the read is empty instead of painting an empty table", () => {
    const html = render({
      navtable: read({ status: "empty", lines: ["This read returned no values."], asOf: null }),
    });
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("No NAV series in this read.");
    expect(html).toContain("This read returned no values.");
    expect(html).not.toContain("NAV index over");
  });

  it("announces an error and repeats the route's own message", () => {
    const html = render({
      navtable: read({ status: "error", lines: ["/nav-series failed (503): upstream unavailable"], asOf: null }),
    });
    expect(html).toContain('role="alert"');
    expect(html).toContain("NAV series could not be read.");
    expect(html).toContain("/nav-series failed (503): upstream unavailable");
  });

  it("withholds a stub envelope rather than painting its numbers", () => {
    const html = render({
      navtable: read({ status: "stub", lines: [STUB_READ], asOf: null }, NAV),
    });
    expect(html).toContain('data-state="withheld"');
    expect(html).toContain("NAV series withheld.");
    expect(html).not.toContain("100.00");
  });

  it("invents nothing from a payload it does not recognise", () => {
    const unknown = render({ navtable: read(OK, { unexpected: true }) });
    expect(unknown).toContain('data-state="empty"');
    expect(unknown).toContain("points not in payload");
    expect(unknown).not.toContain("0.00");

    // A point that carries a date and no level is `—` with its reason, not a zero.
    const sparse = render({ navtable: read(OK, { points: [{ date: "2026-09-24" }] }) });
    expect(sparse).toContain("—");
    expect(sparse).toContain("index not in payload");
    expect(sparse).not.toContain("0.00");
  });
});

describe("tearsheet benchmarks block", () => {
  it("renders one row per close, aligned by column role", () => {
    const html = render({ benchmarks: read(OK, BENCHMARKS) });
    expect(html).toContain('data-route="/benchmarks"');
    expect(html).toContain("Benchmarks · aligned");
    for (const value of ["SPY", "QQQ", "512.30", "514.10", "448.75", "2026-09-23"]) {
      expect(html).toContain(value);
    }
    // Summary: universe, overlap and the aligned start.
    expect(html).toContain("21");
    expect(html).toContain("2025-09-24");
    expect(html).toContain("healthy");
    // ticker is the pinned row label; date and close are numeric columns.
    expect(html).toContain('data-col="key"');
    expect(html.match(/data-col="num"/g)?.length ?? 0).toBeGreaterThanOrEqual(6);
  });

  it("shows the API's own reason when the aligned series is empty", () => {
    const html = render({
      benchmarks: read(OK, { ...BENCHMARKS, series: {}, reason: "no_overlap" }),
    });
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("No aligned benchmark closes in this read.");
    expect(html).toContain("no_overlap");
    expect(html).not.toContain("SPY");
  });

  it("announces an error", () => {
    const html = render({
      benchmarks: read({ status: "error", lines: ["/benchmarks failed (500): market down"], asOf: null }),
    });
    expect(html).toContain('role="alert"');
    expect(html).toContain("Benchmarks could not be read.");
    expect(html).toContain("/benchmarks failed (500): market down");
  });

  it("invents nothing from a payload it does not recognise", () => {
    const html = render({ benchmarks: read(OK, { unexpected: true }) });
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("series not in payload");
    expect(html).not.toContain("0.00");

    const missingClose = render({
      benchmarks: read(OK, { series: { SPY: [{ date: "2026-09-24" }] } }),
    });
    expect(missingClose).toContain("—");
    expect(missingClose).toContain("close not in payload");
    expect(missingClose).not.toContain("0.00");
  });
});

describe("the rest of the tearsheet", () => {
  it("leaves the panes without a block on their PaneBody", () => {
    const html = render({
      navtable: read(OK, NAV),
      benchmarks: read(OK, BENCHMARKS),
      performance: read({ status: "error", lines: ["/performance failed (500): book down"], asOf: null }),
      drawdown: read({ status: "error", lines: ["/performance/drawdown failed (500): series down"], asOf: null }),
    });
    expect(html).toContain("/performance failed (500): book down");
    expect(html).toContain("/performance/drawdown failed (500): series down");
    for (const title of ["Performance · tearsheet", "NAV · by date", "Benchmarks · aligned", "Drawdown"]) {
      expect(html).toContain(title);
    }
    expect(html).toContain('data-route="/performance/drawdown"');
  });
});
