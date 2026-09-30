import { describe, expect, it } from "vitest";

import { architectureEntrance } from "./architectureEntrance";

const vh = 844;

describe("architectureEntrance", () => {
  it("waits while the band is still below the viewport", () => {
    expect(architectureEntrance({ top: 1200, bottom: 3000, height: 1800 }, vh)).toBe("wait");
  });

  it("shows the finished drawing when a later diagram is on screen and the first is above", () => {
    expect(architectureEntrance({ top: -900, bottom: 900, height: 1800 }, vh)).toBe("done");
  });

  it("shows the finished drawing when the reader loaded below the band", () => {
    expect(architectureEntrance({ top: -2400, bottom: -600, height: 1800 }, vh)).toBe("done");
  });

  it("waits until a zero-height band has laid out", () => {
    expect(architectureEntrance({ top: 0, bottom: 0, height: 0 }, vh)).toBe("wait");
  });
});
