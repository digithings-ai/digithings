import { describe, expect, it } from "vitest";
import { LIT_SHADE, REST_SHADE, wordmarkLines } from "./digivoice-wordmark.js";

function brightKey(tMs: number): string {
  return wordmarkLines("DIGIVOICE", { cols: 100, tMs, truecolor: true })
    .cubes.map((cube) => (cube.bright ? "1" : "0"))
    .join("");
}

describe("digivoice hero", () => {
  it("keeps the equalizer on gray and white", () => {
    expect(REST_SHADE.rgb).toBe(135);
    expect(LIT_SHADE.rgb).toBe(255);
    const drawn = wordmarkLines("DIGIVOICE", { cols: 100, tMs: 0, truecolor: true });
    expect(drawn.cubes.length).toBeGreaterThan(0);
    expect(drawn.cubes.some((cube) => cube.bright)).toBe(true);
    expect(drawn.cubes.some((cube) => !cube.bright)).toBe(true);
  });

  it("moves the columns on the same clock as the TUI", () => {
    expect(brightKey(0)).not.toBe(brightKey(400));
  });
});