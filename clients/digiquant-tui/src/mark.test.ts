import { readFileSync } from "node:fs";
import { expect, test } from "bun:test";
import { DIGIQUANT } from "../../../packages/hero-banner/src/definitions/index.ts";
import { PIXEL_7X10 } from "../../../packages/hero-banner/src/font.ts";
import {
  GLINT_EVERY_MS,
  GLINT_MS,
  MARK_GLYPHS,
  MARK_PIXEL_W,
  MARK_SAMPLE_Y,
  MARK_WORD,
  REVEAL_MS,
  glintCell,
  markDirection,
  markElapsed,
  markFilled,
  markLines,
  resetMarkClock,
  revealedColumns,
} from "./mark";

test("the terminal hero uses the web DIGIQUANT cells", () => {
  // The web hero and the terminal mark read one definition (packages/hero-banner,
  // #4986). Reading the definition, not the component's JSX, is the contract: the
  // component only renders `DIGIQUANT`, so a cell change there reaches the web
  // without a terminal edit — and this test says so.
  expect(DIGIQUANT.text).toBe(MARK_WORD);
  const overrides = DIGIQUANT.glyphs as Readonly<Record<string, readonly string[]>>;
  const cells = MARK_GLYPHS as Readonly<Record<string, readonly string[]>>;
  for (const letter of DIGIQUANT.text) {
    expect(overrides[letter] ?? PIXEL_7X10.glyphs[letter]).toEqual(cells[letter]);
  }

  const component = readFileSync(
    new URL("../../../apps/digiquant-web/app/_chrome/QuantWordmark.tsx", import.meta.url),
    "utf8",
  );
  expect(component).toContain("def={DIGIQUANT}");
});

test("the header mark is two braille rows of the web glyphs", () => {
  const lines = markLines();
  expect(lines).toHaveLength(2);
  expect(lines[0]?.length).toBe(40);
  const dots = [
    [0x01, 0x08],
    [0x02, 0x10],
    [0x04, 0x20],
    [0x40, 0x80],
  ];
  for (let row = 0; row < lines.length; row++) {
    const line = lines[row] ?? "";
    for (let col = 0; col < line.length; col++) {
      const ch = line[col] ?? " ";
      const bits = ch === " " ? 0 : (ch.codePointAt(0) ?? 0) - 0x2800;
      expect(bits).toBeGreaterThanOrEqual(0);
      expect(bits).toBeLessThanOrEqual(0xff);
      for (let i = 0; i < dots.length; i++) {
        const y = MARK_SAMPLE_Y[row * 4 + i] ?? -1;
        const dot = dots[i] ?? [0, 0];
        expect(markFilled(col * 2, y)).toBe((bits & dot[0]) !== 0);
        expect(markFilled(col * 2 + 1, y)).toBe((bits & dot[1]) !== 0);
      }
    }
  }
  expect(markFilled(0, 0)).toBe(true);
  expect(markFilled(6, 0)).toBe(false);
});

test("the reveal plays once per process, then one cell glints", () => {
  expect(markLines(0).every((line) => line.trim() === "")).toBe(true);
  expect(revealedColumns(0)).toBe(0);
  expect(revealedColumns(REVEAL_MS)).toBe(MARK_PIXEL_W);
  expect(markLines(MARK_PIXEL_W)).toEqual(markLines());
  expect(glintCell(0)).toBeNull();
  expect(glintCell(REVEAL_MS + GLINT_EVERY_MS - 1)).toBeNull();
  const glint = glintCell(REVEAL_MS + GLINT_EVERY_MS);
  expect(glint).not.toBeNull();
  const full = markLines();
  expect(full[glint?.row ?? 0]?.[glint?.col ?? 0]).not.toBe(" ");
  expect(glintCell(REVEAL_MS + GLINT_EVERY_MS + GLINT_MS)).toBeNull();

  resetMarkClock();
  expect(markElapsed(5_000)).toBe(0);
  expect(markElapsed(5_000 + 40)).toBe(40);
  expect(markElapsed(5_000 + REVEAL_MS + 10)).toBe(REVEAL_MS + 10);
});

test("the reveal mixes up and down across the filled cells", () => {
  const seen = new Set<"up" | "down">();
  const lines = markLines();
  for (let row = 0; row < lines.length; row++) {
    const line = lines[row] ?? "";
    for (let col = 0; col < line.length; col++) {
      if (line[col] === " ") continue;
      seen.add(markDirection(row, col));
    }
  }
  expect(seen).toEqual(new Set(["up", "down"]));
});
