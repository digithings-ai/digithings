import { describe, expect, test } from "bun:test";
import { captureDeskPane } from "./capture";

/**
 * The export half of D9: the desk renders, its reads land, the main desk pane
 * is recorded, and the rail beside it is left out. These assertions read a
 * real render through `captureCharFrame()`, so a crop that drifts from the
 * desk's geometry fails here instead of shipping a frame with the page list in
 * it.
 *
 * The desk is read through the fixture API, so the frame holds the desk's own
 * content: a capture that recorded a loading block or an unreachable-API line
 * would ship a terminal full of errors, and both are refused here.
 */

describe("the recorded frame export", () => {
  test("it records the main desk pane, not the rail beside it", async () => {
    const record = await captureDeskPane({ capturedAt: "2026-10-22T09:00:00.000Z" });
    expect(record.source).toBe("digiquant-tui");
    expect(record.path).toBe("/brief");
    expect(record.capturedAt).toBe("2026-10-22T09:00:00.000Z");
    expect(record.width).toBeGreaterThan(0);
    expect(record.height).toBeGreaterThan(0);
    // The desk's own content is in.
    expect(record.frame).toContain("Brief");
    expect(record.frame).toContain("as of");
    // Nothing was still loading, and nothing failed to load.
    expect(record.frame).not.toContain("loading");
    expect(record.frame).not.toContain("could not be reached");
    // The rail is not.
    expect(record.frame).not.toContain("/portfolio/attribution");
    expect(record.frame).not.toContain("~/pages");
    // The header band is not.
    expect(record.frame).not.toContain("desk:");
  }, 60000);

  test("it records the crop geometry of the pane", async () => {
    const record = await captureDeskPane({});
    const rows = record.frame.split("\n");
    // The pane starts on the pane's own border, not on a rule.
    expect(rows[0].startsWith("┌")).toBe(true);
    // No row is only a rule: the header rule and the footer rule are gone.
    expect(rows.some((row) => row.trim().length > 0 && /^─+$/.test(row.trim()))).toBe(false);
    // Every row fits the width the record claims.
    expect(Math.max(...rows.map((row) => row.length))).toBeLessThanOrEqual(record.width);
  }, 60000);

  test("it records the desk page it was driven to", async () => {
    const record = await captureDeskPane({ path: "/portfolio" });
    expect(record.path).toBe("/portfolio");
    expect(record.frame).toContain("Exposure");
    expect(record.frame).not.toContain("~/pages");
  }, 60000);

  test("it refuses a path the desk does not have", async () => {
    // A record that names a page the frame does not show is a lie the
    // dashboard would print in its summary line.
    await expect(captureDeskPane({ path: "/nope" })).rejects.toThrow(/did not open/);
  }, 60000);
});
