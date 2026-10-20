import { expect, test } from "bun:test";

import {
  CYCLE_MS,
  WORD,
  cellSgr,
  heroSlots,
  wordmarkLines,
} from "../../../packages/ui/src/components/chat/digichat-wordmark";

test("the header wordmark is five half-block rows in one color mode", () => {
  expect(CYCLE_MS).toBe(2640);
  const drawn = wordmarkLines("DIGICHAT", { cols: 96, tMs: 2000, truecolor: true });
  expect(drawn.rows).toBe(5);
  const text = drawn.lines.map((row) => row.map((cell) => cell.ch).join("")).join("\n");
  expect(text).toMatch(/[█▀▄]/);
  for (const cell of drawn.lines.flat()) {
    const sgr = cellSgr(cell);
    expect(sgr.includes("38;5") && sgr.includes("38;2")).toBe(false);
    if (cell.ch === " ") expect(cell.color).toBeNull();
  }
});

test("a later moment in the same process does not scramble again", () => {
  const later = heroSlots(CYCLE_MS + 50, true);
  expect(later.map((slot) => slot.ch).join("")).toBe("DIGICHAT");
  expect(later.some((slot) => slot.shade === "dim")).toBe(false);
  expect(WORD).toBe("DIGICHAT");
});
