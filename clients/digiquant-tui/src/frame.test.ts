import { describe, expect, test } from "bun:test";
import {
  cropMainDeskPane,
  HEADER_ROWS,
  makeRecordedFrame,
  RAIL_COLS_DEFAULT,
  serializeRecordedFrame,
} from "./frame";

/** A rail row: the page list ends with its right border in the last rail column. */
function rail(text: string): string {
  return text.padEnd(RAIL_COLS_DEFAULT - 1, " ") + "│";
}

/**
 * A captured frame in the desk's real geometry: a header band, a rule, the
 * rail beside the desk body, then the footer rule. The rail text is the
 * control: a crop that keeps it kept the page list, not the pane.
 */
const CAPTURED = [
  "  desk: Baseline ▾  /brief",
  "",
  "─".repeat(70),
  rail(" ~/pages") + "┌──────────┐",
  rail(" ▸ /brief") + "│ Brief    │",
  rail(" ▸ /portfolio/holdings") + "│ Exposure │",
  rail("") + "└──────────┘",
  rail(""),
  "─".repeat(70),
].join("\n");

describe("the main desk pane crop", () => {
  test("it keeps the desk body and drops the rail beside it", () => {
    const cropped = cropMainDeskPane(CAPTURED);
    expect(cropped.frame).toBe(
      ["┌──────────┐", "│ Brief    │", "│ Exposure │", "└──────────┘"].join("\n"),
    );
    expect(cropped.frame).not.toContain("/portfolio/holdings");
    expect(cropped.frame).not.toContain("~/pages");
  });

  test("it drops the header band and the footer rule", () => {
    const cropped = cropMainDeskPane(CAPTURED);
    expect(cropped.frame).not.toContain("desk:");
    // The header rule and the footer rule are full-width rules. The pane's own
    // borders are not, so the first row of the crop starts the pane.
    expect(cropped.frame.split("\n").some((line) => line.startsWith("───"))).toBe(false);
    expect(cropped.frame.split("\n")[0].startsWith("┌")).toBe(true);
  });

  test("it drops the footer rule from a capture that ends with a newline", () => {
    // `captureCharFrame()` ends the frame with a newline, so the captured
    // string carries an empty tail. That tail is not a row: the row before it
    // is the footer rule, and the crop has to stop one row short of it.
    const cropped = cropMainDeskPane(`${CAPTURED}\n`);
    expect(cropped.frame).toBe(
      ["┌──────────┐", "│ Brief    │", "│ Exposure │", "└──────────┘"].join("\n"),
    );
    expect(cropped.height).toBe(4);
  });

  test("it refuses a capture that has no pane in it", () => {
    // A capture narrower than the rail holds no desk pane. A record with an
    // empty frame would be dropped by the dashboard without a word, so the
    // crop fails instead.
    expect(() => cropMainDeskPane(`  desk: Baseline ▾  /brief\n\n${"─".repeat(20)}\n`)).toThrow(
      /empty/,
    );
  });

  test("it reports the size of the frame it cropped", () => {
    const cropped = cropMainDeskPane(CAPTURED);
    expect(cropped.width).toBe(12);
    expect(cropped.height).toBe(4);
  });

  test("it reads the header band height from the mark, not from a guess", () => {
    // The header band is the mark's rows plus its rule row.
    expect(HEADER_ROWS).toBe(3);
  });
});

describe("the recorded frame record", () => {
  test("it carries the source, the path, the capture time and the frame", () => {
    const record = makeRecordedFrame({
      source: "digiquant-tui",
      path: "/brief",
      capturedAt: "2026-10-22T09:00:00.000Z",
      cropped: cropMainDeskPane(CAPTURED),
    });
    expect(record.source).toBe("digiquant-tui");
    expect(record.path).toBe("/brief");
    expect(record.capturedAt).toBe("2026-10-22T09:00:00.000Z");
    expect(record.width).toBe(12);
    expect(record.height).toBe(4);
    expect(record.frame).toContain("Brief");
  });

  test("it serializes to JSON that reads back to the same record", () => {
    const record = makeRecordedFrame({
      source: "digiquant-tui",
      path: "/brief",
      capturedAt: "2026-10-22T09:00:00.000Z",
      cropped: cropMainDeskPane(CAPTURED),
    });
    const raw = serializeRecordedFrame(record);
    expect(raw.endsWith("\n")).toBe(true);
    expect(JSON.parse(raw)).toEqual(record);
  });
});
