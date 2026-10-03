import { describe, expect, it } from "vitest";

import {
  CYCLE_MS,
  FLASH_MS,
  HOLD_MS,
  LOCK_MS,
  POOL,
  SETTLED_MS,
  SHADES,
  SPIN_MS,
  STEP_MS,
  WORD,
  cellSgr,
  glyphOf,
  letterGap,
  slotsAt,
  truecolorEnabled,
  wordmarkLines,
  wordmarkPixels,
} from "./digichat-wordmark";

const HERO = {
  D: ["######.", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", "######."],
  I: ["#######", "#######", "..##...", "..##...", "..##...", "..##...", "..##...", "..##...", "#######", "#######"],
  G: [".#####.", "#######", "##.....", "##.....", "##..###", "##..###", "##...##", "##...##", "#######", ".#####."],
  C: [".#####.", "#######", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "#######", ".#####."],
  H: ["##...##", "##...##", "##...##", "##...##", "#######", "#######", "##...##", "##...##", "##...##", "##...##"],
  T: ["#######", "#######", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##..", "...##.."],
};

describe("digichat wordmark", () => {
  it("is a 2.64s lock cycle of 7×10 square cells", () => {
    expect(CYCLE_MS).toBe(2640);
    expect(SPIN_MS + 8 * LOCK_MS + HOLD_MS).toBe(CYCLE_MS);
    expect(STEP_MS).toBe(80);
    expect(letterGap(120, 8)).toBe(2);
    for (const [ch, rows] of Object.entries(HERO)) {
      expect(glyphOf(ch)).toEqual(rows);
    }
    for (const ch of `${WORD}${POOL}`) {
      const rows = glyphOf(ch);
      expect(rows, ch).toHaveLength(10);
      expect(rows?.every((row) => row.length === 7 && /^[#.]+$/.test(row))).toBe(true);
    }
  });

  it("cycles dim, flashes white, then rests brighter gray, left to right", () => {
    const start = slotsAt(0);
    expect(start).toHaveLength(8);
    expect(start.every((slot) => slot.shade === "dim" && slot.ch && POOL.includes(slot.ch))).toBe(true);
    expect(start.map((slot) => slot.ch).join("")).not.toBe(WORD);

    const firstLock = slotsAt(SPIN_MS);
    expect(firstLock[0]).toEqual({ ch: "D", shade: "flash" });
    expect(firstLock[1]?.shade).toBe("dim");

    const afterFlash = slotsAt(SPIN_MS + FLASH_MS);
    expect(afterFlash[0]).toEqual({ ch: "D", shade: "rest" });

    const settled = slotsAt(SETTLED_MS);
    expect(settled.map((slot) => slot.ch).join("")).toBe(WORD);
    expect(settled.every((slot) => slot.shade === "rest")).toBe(true);

    expect(slotsAt(CYCLE_MS).map((slot) => slot.ch)).toEqual(start.map((slot) => slot.ch));
  });

  it("skips a missing glyph and never throws", () => {
    expect(() => slotsAt(0, "~")).not.toThrow();
    expect(slotsAt(SETTLED_MS, "~")[0]?.ch).toBeNull();
    const lines = wordmarkLines("~", { tMs: SETTLED_MS, truecolor: true });
    expect(lines.rows).toBe(5);
    expect(lines.lines.flat().every((cell) => cell.ch === " " && cell.color === null)).toBe(true);
  });

  it("draws half-blocks in one color mode and leaves gaps dark", () => {
    const cube = wordmarkLines(WORD, { cols: 120, tMs: SETTLED_MS, truecolor: false });
    const rgb = wordmarkLines(WORD, { cols: 120, tMs: SETTLED_MS, truecolor: true });
    expect(cube.rows).toBe(5);
    expect(cube.gap).toBe(2);
    const drawn = cube.lines.flat().map((cell) => cell.ch).join("");
    expect(drawn).toMatch(/[█▀▄]/);
    expect(drawn).toMatch(/^[\s█▀▄]+$/);
    for (const cell of cube.lines.flat()) {
      const sgr = cellSgr(cell);
      expect(sgr.includes("38;5") && sgr.includes("38;2")).toBe(false);
      if (cell.ch === " ") {
        expect(cell.color).toBeNull();
        expect(sgr).toBe("");
        continue;
      }
      expect(cell.color && "cube" in cell.color).toBe(true);
      expect(cell.color && "rgb" in cell.color).toBe(false);
      expect(sgr.startsWith("38;5;")).toBe(true);
      expect(sgr).not.toContain("38;2");
    }
    for (const cell of rgb.lines.flat()) {
      const sgr = cellSgr(cell);
      expect(sgr.includes("38;5") && sgr.includes("38;2")).toBe(false);
      if (!cell.color) continue;
      expect("rgb" in cell.color).toBe(true);
      expect("cube" in cell.color).toBe(false);
      expect(sgr).toBe(`38;2;${SHADES.rest.rgb};${SHADES.rest.rgb};${SHADES.rest.rgb}`);
    }
    const gap = cube.lines[0]?.slice(7, 9) ?? [];
    expect(gap.every((cell) => cell.ch === " " && cell.color === null)).toBe(true);
  });

  it("uses 38;2 only for truecolor and 24bit", () => {
    expect(truecolorEnabled("truecolor")).toBe(true);
    expect(truecolorEnabled("24bit")).toBe(true);
    expect(truecolorEnabled("TRUECOLOR")).toBe(true);
    expect(truecolorEnabled("")).toBe(false);
    expect(truecolorEnabled(undefined)).toBe(false);
    expect(truecolorEnabled("256color")).toBe(false);
  });

  it("keeps web pixels square and on the settled gray", () => {
    const mark = wordmarkPixels(SETTLED_MS, { gap: 1 });
    expect(mark.height).toBe(10);
    expect(mark.width).toBe(8 * 7 + 7);
    expect(mark.pixels.every((pixel) => pixel.shade === "rest")).toBe(true);
    expect(mark.pixels.some((pixel) => pixel.x === 7)).toBe(false);
  });
});
