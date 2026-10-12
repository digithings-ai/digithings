/**
 * DIG-2848: the devkit header mark is the universal digichat hero banner, in
 * the compact cell encoding, so it is small enough for the top-left corner and
 * still runs the definition's own scramble LOADING and LIVE animation.
 */
import { testRender } from "@opentui/react/test-utils";
import { afterEach, describe, expect, test } from "bun:test";

import { DIGICHAT } from "../../../packages/hero-banner/src/definitions";
import { preparedBanner } from "../../../packages/hero-banner/src/engine";
import { compactLines } from "../../../packages/hero-banner/src/tui";
import { MARK_COLS, MARK_ROWS, DigichatMark } from "./wordmark";

let current: Awaited<ReturnType<typeof testRender>> | null = null;

afterEach(() => {
  current?.renderer.destroy();
  current = null;
  delete process.env.DIGICHAT_DEVKIT_MARK_MS;
  delete process.env.NO_MOTION;
  delete process.env.HERO_BANNER_LIVE;
});

/** The frame the devkit header draws at `DIGICHAT_DEVKIT_MARK_MS = t`. */
async function frameAt(t: number, size = { width: 120, height: 34 }): Promise<string> {
  process.env.DIGICHAT_DEVKIT_MARK_MS = String(t);
  current?.renderer.destroy();
  current = await testRender(<DigichatMark />, size);
  await current.renderOnce();
  return current.captureCharFrame();
}

const rows = (frame: string) => frame.split("\n").filter((line) => /[\u2800-\u28ff]/.test(line));

const loadingMs = DIGICHAT.animation.loadingMs(preparedBanner(DIGICHAT).state);

describe("devkit header mark", () => {
  test("is the definition's compact mark: two rows, the definition's width", async () => {
    const frame = await frameAt(100_000);
    expect(rows(frame)).toHaveLength(MARK_ROWS);
    expect(MARK_ROWS).toBe(2);
    expect(MARK_COLS).toBe(35); // 8 glyphs x 7 pixel columns, gap 2: 70 columns, two to a cell
    for (const line of rows(frame)) expect(line.trimEnd().length).toBeLessThanOrEqual(MARK_COLS);
  });

  for (const size of [
    { width: 120, height: 34 },
    { width: 80, height: 24 },
  ]) {
    test(`${size.width}x${size.height}: LOADING plays, then settles on the mark`, async () => {
      process.env.NO_MOTION = "1";
      const settled = await frameAt(0, size);
      delete process.env.NO_MOTION;

      const early = await frameAt(0, size);
      const mid = await frameAt(Math.round(loadingMs * 0.35), size);
      expect(rows(early)).toHaveLength(MARK_ROWS);
      expect(early).not.toBe(mid); // the scramble moves
      expect(mid).not.toBe(settled); // and has not settled yet

      const done = await frameAt(loadingMs + 1, size);
      expect(done).toBe(settled);
      for (const line of done.split("\n")) expect(line.length).toBeLessThanOrEqual(size.width);
    });
  }

  test("NO_MOTION and LIVE=0 both settle", async () => {
    process.env.NO_MOTION = "1";
    expect(await frameAt(0)).toBe(await frameAt(900_000));
    delete process.env.NO_MOTION;
    process.env.HERO_BANNER_LIVE = "0";
    expect(await frameAt(100_000)).toBe(await frameAt(140_000));
  });

  test("the cells carry the definition's own tones, flash included", () => {
    // captureCharFrame() reads characters only, and the DIGICHAT LIVE pulse is a
    // colour change. Pin it on the encoding the header actually draws.
    const tones = new Set<string>();
    for (let t = 0; t < 20_000; t += 200) {
      for (const row of compactLines(DIGICHAT, { t: loadingMs + t, mode: "truecolor" }).lines) {
        for (const cell of row) if (cell.fg && "hex" in cell.fg) tones.add(cell.fg.hex);
      }
    }
    // the renderer lowercases hex, so compare on the same form
    expect(tones.has(DIGICHAT.palette.rest.hex.toLowerCase())).toBe(true); // the settled mark
    expect(tones.has(DIGICHAT.palette.flash.hex.toLowerCase())).toBe(true); // the live pulse
  });
});