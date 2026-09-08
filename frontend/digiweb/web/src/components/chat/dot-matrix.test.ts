import { describe, expect, it } from "vitest";

import { litCellsFor, PATTERNS, type DotMatrixState } from "./DotMatrix";

const CHROME: readonly DotMatrixState[] = [
  "copy",
  "edit",
  "attach",
  "send",
  "more",
  "refresh",
  "export",
  "download",
  "stop",
  "remove",
  "scroll",
  "prev",
  "next",
  "dictate",
  "plus",
  "expand",
  "user",
  "assistant",
  "example",
  "system",
  "warning",
  "error",
  "success",
];

describe("DotMatrix chrome glyphs", () => {
  it("gives every chrome state a single static frame", () => {
    for (const state of CHROME) {
      expect(PATTERNS[state].length, state).toBe(1);
      expect(litCellsFor(state).length, state).toBeGreaterThan(0);
    }
  });

  it("keeps each chrome pattern distinct", () => {
    const signatures = CHROME.map((state) =>
      [...litCellsFor(state)].sort((a, b) => a - b).join(","),
    );
    expect(new Set(signatures).size).toBe(CHROME.length);
  });

  it("encodes role arrows as distinct chevrons", () => {
    expect(litCellsFor("user")).toEqual([1, 7, 13, 17, 21]);
    expect(litCellsFor("assistant")).toEqual([0, 5, 6, 10, 11, 12, 15, 16, 20]);
    expect(litCellsFor("example")).toEqual([2, 8, 14, 18, 22]);
  });
});
