import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { loopProgress, matrixTranslateX, resumeDelaySeconds } from "./Marquee";

describe("marquee hover hold", () => {
  it("reads the current translation from a computed matrix", () => {
    expect(matrixTranslateX("none")).toBe(0);
    expect(matrixTranslateX("matrix(1, 0, 0, 1, -240, 0)")).toBe(-240);
    expect(matrixTranslateX("translateX(-80px)")).toBe(-80);
    expect(matrixTranslateX("rotate(4deg)")).toBeNull();
  });

  it("keeps progress inside one loop for both directions", () => {
    expect(loopProgress(0, 400, "left")).toBe(0);
    expect(loopProgress(-100, 400, "left")).toBeCloseTo(0.25);
    expect(loopProgress(-400, 400, "left")).toBe(0);
    expect(loopProgress(-400, 400, "right")).toBe(0);
    expect(loopProgress(-300, 400, "right")).toBeCloseTo(0.25);
    expect(loopProgress(0, 400, "right")).toBe(0);
  });

  it("resumes with a negative delay at the same progress", () => {
    expect(resumeDelaySeconds(0.25, 48)).toBe("-12s");
    expect(resumeDelaySeconds(0, 48)).toBe("-0s");
  });

  it("does not pause the track by restarting the animation on hover", () => {
    const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../styles/marquee.css"), "utf8");
    expect(css).not.toMatch(/\.mq-row:hover[^{]*\{[^}]*animation/);
    expect(css).toContain('.mq-row[data-paused="true"] .mq-track');
    expect(css).toContain("animation-play-state: paused");
  });
});
