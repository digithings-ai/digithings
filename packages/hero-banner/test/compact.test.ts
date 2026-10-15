import { describe, expect, test } from "bun:test";

import { DIGICHAT } from "../src/definitions";
import { preparedBanner } from "../src/engine";
import { canonicalLayout } from "../src/layout";
import { COMPACT_SAMPLE_Y, compactLines, toPlain } from "../src/tui";
import type { TermCell } from "../src/tui";

const BRAILLE = /^[\u2800-\u28ff ]$/;
const dots = (line: string) => [...line].map((ch) => (ch === " " ? 0 : ch.charCodeAt(0) - 0x2800));

/** The dot mask the definition's own layout and sampled rows produce: the
 *  packing, with no animation and no renderer involved. */
function expectedMask(layout: ReturnType<typeof canonicalLayout>): string[] {
  const rows: string[] = [];
  for (let row = 0; row < COMPACT_SAMPLE_Y.length; row += 4) {
    let line = "";
    for (let col = 0; col < Math.ceil(layout.width / 2); col += 1) {
      const x = col * 2;
      let bits = 0;
      for (let i = 0; i < 4; i += 1) {
        const y = COMPACT_SAMPLE_Y[row + i] ?? -1;
        for (let dx = 0; dx < 2; dx += 1) {
          const px = x + dx;
          let lit = false;
          for (let g = 0; g < layout.text.length && !lit; g += 1) {
            const start = layout.starts[g] ?? 0;
            if (px < start || px >= start + layout.font.cols) continue;
            lit = (layout.font.glyphs[layout.text[g] ?? ""]?.[y] ?? [])[px - start] === "#";
          }
          if (lit) bits |= [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]][i]?.[dx] ?? 0;
        }
      }
      line += bits === 0 ? " " : String.fromCharCode(0x2800 + bits);
    }
    rows.push(line);
  }
  return rows;
}

const flatten = (lines: TermCell[][]) => toPlain(lines);

describe("compact banner cells", () => {
  const { layout, state } = preparedBanner(DIGICHAT);

  test("a small header mark is two rows of the definition's own font", () => {
    const out = compactLines(DIGICHAT, { t: 100_000, mode: "256" });
    expect(out.lines).toHaveLength(2);
    expect(out.width).toBe(Math.ceil(layout.width / 2));
    expect(out.width).toBe(35); // 8 glyphs x 7 columns, gap 2: 70 pixel columns
    for (const line of flatten(out.lines)) expect(line).toMatch(new RegExp(`^[\\u2800-\\u28ff ]{${out.width}}$`));
  });

  test("the packed cells are the DIGICHAT definition, not a local wordmark", () => {
    const out = compactLines(DIGICHAT, { t: 100_000, motion: "reduced", mode: "256" });
    expect(flatten(out.lines)).toEqual(expectedMask(layout));
    expect(dots(flatten(out.lines)[0] ?? "")).not.toEqual(dots(flatten(out.lines)[1] ?? ""));
  });

  test("LOADING plays once per mount and animates while it runs", () => {
    const loadingMs = DIGICHAT.animation.loadingMs(state);
    expect(compactLines(DIGICHAT, { t: 0, mode: "256" }).phase).toBe("loading");
    const frames = [0, 120, 300].map((t) => flatten(compactLines(DIGICHAT, { t, mode: "256" }).lines).join("\n"));
    expect(new Set(frames).size).toBe(3);
    expect(compactLines(DIGICHAT, { t: loadingMs, mode: "256" }).phase).not.toBe("loading");
  });

  test("LIVE runs on and its flash reaches the cells", () => {
    expect(compactLines(DIGICHAT, { t: 100_000, mode: "truecolor" }).phase).toBe("live");
    const lit = new Set<string>();
    for (let t = 0; t < 20_000; t += 120) {
      for (const row of compactLines(DIGICHAT, { t: 100_000 + t, mode: "truecolor" }).lines) {
        for (const cell of row) if (cell.fg && "hex" in cell.fg) lit.add(cell.fg.hex);
      }
    }
    expect(lit.has("#d7d7d7")).toBe(true); // rest / ink, the settled mark
    expect(lit.has("#ffffff")).toBe(true); // flash, the live pulse
  });

  test("reduced motion settles: one mark, whatever the clock says", () => {
    const a = flatten(compactLines(DIGICHAT, { t: 0, motion: "reduced", mode: "256" }).lines).join("\n");
    const b = flatten(compactLines(DIGICHAT, { t: 900_000, motion: "reduced", mode: "256" }).lines).join("\n");
    expect(a).toBe(b);
    expect(compactLines(DIGICHAT, { t: 0, motion: "reduced", mode: "256" }).phase).toBe("still");
  });
});