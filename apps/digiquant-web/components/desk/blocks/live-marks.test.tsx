import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { STUB_READ, type ReadResult } from "digiquant-tui/read";
import { LiveMarksBlock } from "./live-marks";

const OK: ReadResult = { status: "ok", lines: [], asOf: "2026-09-24" };

const PAYLOAD = {
  quote_date: "2026-09-24",
  live_vs_mark_pct: 0.42,
  day_return_live_pct: -0.28,
  since_inception_live_pct: 12.4,
  excess_live_pct: 1.8,
  overlay_eligible: true,
  universe: ["ABC", "DEF", "GHI"],
};

const render = (read: ReadResult | undefined, data?: unknown) =>
  renderToStaticMarkup(<LiveMarksBlock read={read} data={data} />);

describe("live marks block", () => {
  it("renders every figure the payload carries, with its sign and tone", () => {
    const html = render(OK, PAYLOAD);
    expect(html).toContain("Live vs mark");
    expect(html).toContain("+0.42%");
    expect(html).toContain("-0.28%");
    expect(html).toContain("+12.40%");
    expect(html).toContain("+1.80%");
    expect(html).toContain("Day (live)");
    expect(html).toContain("Since inception (live)");
    expect(html).toContain("Excess (live)");
    expect(html).toContain("Overlay");
    expect(html).toContain("eligible");
    // The one line this read must always carry.
    expect(html).toContain("live marks");
    expect(html).toContain("not finalized accounting");
    expect(html).toContain("quotes 2026-09-24");
    expect(html).toContain("ABC DEF GHI");
    // Nothing is missing, so the missing mark is not painted anywhere.
    expect(html).not.toContain("—");
    expect(html).not.toContain('data-state="missing"');
  });

  it("says the read is empty instead of painting a grid of dashes", () => {
    const html = render({ status: "empty", lines: ["This read returned no values."], asOf: null }, null);
    expect(html).toContain('data-state="empty"');
    expect(html).toContain("No live marks in this read.");
    expect(html).toContain("This read returned no values.");
    expect(html).not.toContain("Live vs mark");
  });

  it("announces an error and repeats the route's own message", () => {
    const html = render(
      { status: "error", lines: ["/kpis/live failed (503): upstream unavailable"], asOf: null },
      null,
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain("[!]");
    expect(html).toContain("Live marks could not be read.");
    expect(html).toContain("/kpis/live failed (503): upstream unavailable");
    expect(html).not.toContain("Live vs mark");
  });

  it("withholds a stub envelope rather than showing its numbers", () => {
    const html = render({ status: "stub", lines: [STUB_READ], asOf: null }, { live_vs_mark_pct: 99.909 });
    expect(html).toContain('data-state="withheld"');
    expect(html).toContain("Live marks withheld.");
    expect(html).toContain(STUB_READ);
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("Live vs mark");
  });

  it("reads as loading before the first response lands", () => {
    const html = render(undefined, undefined);
    expect(html).toContain('data-state="loading"');
    expect(html).toContain("reading /kpis/live");
  });

  it("omits the sparkline when the read carries no series", () => {
    const html = render(OK, PAYLOAD);
    expect(html).not.toContain("<svg");
    expect(html).not.toContain("sparkline");
  });

  it("draws the sparkline when a series is present, and says so when it is too short", () => {
    const drawn = render(OK, { ...PAYLOAD, series: [0.1, 0.4, 0.2, 0.55] });
    expect(drawn).toContain("<svg");
    expect(drawn).toContain("live marks over 4 points");

    const tooShort = render(OK, { ...PAYLOAD, series: [0.1] });
    expect(tooShort).not.toContain("<svg");
    expect(tooShort).toContain("live marks · no series in this read");
  });

  it("leaves a null field as — with its reason, never as a zero", () => {
    const html = render(OK, { ...PAYLOAD, day_return_live_pct: null, excess_live_pct: undefined });
    expect(html).toContain("—");
    expect(html).toContain("not available");
    expect(html).toContain('data-state="missing"');
    expect(html).not.toContain("0.00%");
  });

  it("does not crash on a payload it does not recognise", () => {
    const shapes: unknown[] = [
      { unexpected: true },
      { live_vs_mark_pct: "0.42", day_return_live_pct: {}, universe: "ABC", series: "nope" },
    ];
    for (const shape of shapes) {
      const html = render(OK, shape);
      expect(html).toContain("Live vs mark");
      expect(html).toContain("—");
    }
    // A non-object payload is withheld, and the reason names what arrived.
    const list = render(OK, [1, 2, 3]);
    expect(list).toContain('data-state="withheld"');
    expect(list).toContain("a list, not an object");
    // A wrong-typed figure names the type it found.
    const wrong = render(OK, { live_vs_mark_pct: "0.42" });
    expect(wrong).toContain("not a number (string)");
  });
});
