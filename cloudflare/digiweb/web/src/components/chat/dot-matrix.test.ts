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
  "up",
  "down",
  "prev",
  "next",
  "dictate",
  "newChat",
  "expand",
  "user",
  "assistant",
  "example",
  "system",
  "thumbsUp",
  "thumbsDown",
  "warning",
  "error",
  "success",
  "thought",
];

function cells(state: DotMatrixState): number[] {
  return [...litCellsFor(state)].sort((a, b) => a - b);
}

function signature(state: DotMatrixState): string {
  return cells(state).join(",");
}

describe("DotMatrix chrome glyphs", () => {
  it("gives every chrome state a single static frame", () => {
    for (const state of CHROME) {
      expect(PATTERNS[state].length, state).toBe(1);
      expect(litCellsFor(state).length, state).toBeGreaterThan(0);
    }
  });

  it("keeps each chrome pattern distinct except documented aliases", () => {
    const aliases = new Set<DotMatrixState>(["next"]);
    const signatures = CHROME.filter((state) => !aliases.has(state)).map(signature);
    expect(new Set(signatures).size).toBe(signatures.length);
  });

  it("pairs attach as the lit plus and new-chat as the 2×2-corner inverse", () => {
    expect(cells("attach")).toEqual([2, 7, 10, 11, 12, 13, 14, 17, 22]);
    expect(cells("newChat")).toEqual([
      0, 1, 3, 4, 5, 6, 8, 9, 15, 16, 18, 19, 20, 21, 23, 24,
    ]);
    expect(signature("newChat")).not.toBe(signature("attach"));
    expect(cells("newChat").every((cell) => !cells("attach").includes(cell))).toBe(true);
  });

  it("uses a 3×3 stop block and corner-bracket system mark", () => {
    expect(cells("stop")).toEqual([6, 7, 8, 11, 12, 13, 16, 17, 18]);
    expect(cells("system")).toEqual([0, 1, 3, 4, 5, 9, 15, 19, 20, 21, 23, 24]);
    expect(signature("stop")).not.toBe(signature("system"));
  });

  it("uses a compact user chevron and a four-cube diamond for examples", () => {
    expect(cells("user")).toEqual([6, 12, 16]);
    expect(cells("example")).toEqual([7, 11, 13, 17]);
    expect(cells("next")).toEqual(cells("user"));
    expect(signature("example")).not.toBe(signature("user"));
    expect(signature("example")).not.toBe(signature("up"));
    expect(signature("example")).not.toBe(signature("down"));
    expect(cells("prev")).toEqual([8, 12, 18]);
    expect(cells("assistant")).toEqual([5, 6, 10, 11, 12, 15, 16]);
  });

  it("snaps redrawn chrome glyphs to readable 5×5 signatures", () => {
    expect(cells("copy")).toEqual([2, 3, 4, 7, 9, 10, 11, 12, 13, 14, 15, 17, 20, 21, 22]);
    expect(cells("edit")).toEqual([0, 1, 2, 3, 4, 7, 12, 17, 20, 21, 22, 23, 24]);
    expect(cells("send")).toEqual([2, 3, 4, 9, 11, 14, 15, 16, 17, 18, 19, 21]);
    expect(cells("more")).toEqual([10, 12, 14]);
    expect(cells("refresh")).toEqual([1, 2, 3, 4, 5, 9, 10, 11, 13, 14, 15, 19, 20, 21, 22, 23]);
    expect(cells("up")).toEqual([7, 11, 13]);
    expect(cells("down")).toEqual([11, 13, 17]);
    expect(cells("expand")).toEqual([7, 13, 17]);
    expect(signature("expand")).not.toBe(signature("down"));
    expect(signature("expand")).not.toBe(signature("next"));
    expect(cells("export")).toEqual([2, 6, 7, 8, 12, 17, 20, 21, 22, 23, 24]);
    expect(cells("download")).toEqual([2, 7, 11, 12, 13, 17, 20, 21, 22, 23, 24]);
    expect(cells("remove")).toEqual([0, 4, 6, 8, 16, 18, 20, 24]);
    expect(cells("scroll")).toEqual([6, 8, 12, 16, 18, 22]);
    expect(signature("scroll")).not.toBe(signature("down"));
    expect(signature("scroll")).not.toBe(signature("download"));
    expect(cells("thumbsUp")).toEqual([0, 1, 5, 6, 10, 11, 12, 13, 14, 15, 19, 20, 21, 22, 23, 24]);
    expect(cells("thumbsDown")).toEqual([0, 1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15, 16, 20, 21]);
    expect(signature("thumbsUp")).not.toBe(signature("thumbsDown"));
    expect(cells("thought")).toEqual([
      1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 17, 21, 22, 23,
    ]);
    expect(PATTERNS.thought.length).toBe(1);
    expect(signature("thought")).not.toBe(signature("success"));
    expect(signature("thought")).not.toBe(signature("stop"));
    expect(signature("thought")).not.toBe(signature("dictate"));
  });
});

describe("DotMatrix motion", () => {
  it("sweeps a dense rim arc for loading, not a single cube", () => {
    expect(PATTERNS.loading.length).toBe(16);
    for (const frame of PATTERNS.loading) {
      expect(new Set(frame).size).toBe(9);
    }
    expect(litCellsFor("thinking").length).toBe(16);
    expect(litCellsFor("loading").length).toBe(9);
  });

  it("presses two bars together for tool execution", () => {
    expect(PATTERNS.tool.length).toBe(8);
    expect([...litCellsFor("tool", 0)].sort((a, b) => a - b)).toEqual([
      0, 1, 2, 3, 4, 20, 21, 22, 23, 24,
    ]);
    expect([...litCellsFor("tool", 2)].sort((a, b) => a - b)).toEqual([
      5, 6, 7, 8, 9, 15, 16, 17, 18, 19,
    ]);
    expect(new Set(litCellsFor("tool", 4)).size).toBe(15);
    expect(litCellsFor("tool", 0)).not.toEqual(litCellsFor("loading"));
  });
});
