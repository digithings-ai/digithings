import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { STUB_READ, type ReadResult } from "digiquant-tui/read";
import type { OfficialRead } from "../read-block";
import { BriefPanes } from "./brief";

const OK: ReadResult = { status: "ok", lines: [], asOf: "2026-09-24" };

const PAYLOAD = {
  quote_date: "2026-09-24",
  live_vs_mark_pct: 0.42,
  day_return_live_pct: -0.28,
  since_inception_live_pct: 12.4,
  excess_live_pct: 1.8,
  overlay_eligible: true,
  universe: ["ABC", "DEF"],
};

const read = (result: ReadResult, data: unknown = null): OfficialRead => ({ result, data });

const render = (reads: Record<string, OfficialRead> = {}) =>
  renderToStaticMarkup(<BriefPanes reads={reads} />);

describe("brief live pane", () => {
  it("paints the live block from the /kpis/live payload", () => {
    const html = render({ live: read(OK, PAYLOAD) });
    expect(html).toContain('data-route="/kpis/live"');
    expect(html).toContain("Live vs mark");
    expect(html).toContain("Day (live)");
    expect(html).toContain("Since inception (live)");
    expect(html).toContain("Excess (live)");
    expect(html).toContain("Overlay");
    expect(html).toContain("+0.42%");
    expect(html).toContain("-0.28%");
    expect(html).toContain("quotes 2026-09-24");
    expect(html).toContain("live marks");
    expect(html).toContain("not finalized accounting");
  });

  it("says the read is empty instead of painting a grid of dashes", () => {
    const html = render({ live: read({ status: "empty", lines: ["This read returned no values."], asOf: null }) });
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("No live marks in this read.");
    expect(html).not.toContain("Live vs mark");
  });

  it("announces an error through the state block", () => {
    const html = render({ live: read({ status: "error", lines: ["/kpis/live failed (503): upstream unavailable"], asOf: null }) });
    expect(html).toContain('role="alert"');
    expect(html).toContain("Live marks could not be read.");
    expect(html).toContain("/kpis/live failed (503): upstream unavailable");
    expect(html).not.toContain("Live vs mark");
  });

  it("withholds a stub envelope rather than painting its numbers", () => {
    const html = render({ live: read({ status: "stub", lines: [STUB_READ], asOf: null }, { live_vs_mark_pct: 99.909 }) });
    expect(html).toContain('data-state="withheld"');
    expect(html).toContain("Live marks withheld.");
    expect(html).toContain(STUB_READ);
    expect(html).not.toContain("99.909");
  });

  it("withholds a stub mark the desk already judged a stub, even on a successful read", () => {
    const html = render({ live: read({ status: "ok", lines: ["99.909"], asOf: null }, { live_vs_mark_pct: 0.42 }) });
    expect(html).toContain('data-state="withheld"');
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("+0.42%");
  });

  it("invents nothing from a payload it does not recognise", () => {
    const html = render({ live: read(OK, { unexpected: true }) });
    expect(html).toContain("Live vs mark");
    expect(html).toContain("—");
    expect(html).toContain("not in payload");
    expect(html).not.toContain("0.00%");
  });

  it("leaves every other brief pane on its PaneBody", () => {
    const html = render({
      live: read(OK, PAYLOAD),
      brief: read({ status: "error", lines: ["/brief failed (500): scoreboard down"], asOf: null }),
      decision: read({ status: "error", lines: ["/brief/decision failed (500): log down"], asOf: null }),
      movers: read({ status: "error", lines: ["/allocations/enriched failed (500): book down"], asOf: null }),
    });
    // The failed panes still paint the official sentence, not a block.
    expect(html).toContain("/brief failed (500): scoreboard down");
    expect(html).toContain("/brief/decision failed (500): log down");
    expect(html).toContain("/allocations/enriched failed (500): book down");
    expect(html).not.toContain('data-state="withheld"');
    // Every catalog pane is still on the page.
    for (const title of [
      "Brief · scoreboard",
      "Live marks · snapshot",
      "Decision",
      "Signals to resolve",
      "What could break the view",
      "Book · movers",
      "Run health",
    ]) {
      expect(html).toContain(title);
    }
  });
});
