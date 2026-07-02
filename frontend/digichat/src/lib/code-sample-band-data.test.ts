import { describe, it, expect } from "vitest";
import { CODE_SAMPLES, getSampleById } from "./code-sample-band-data";

describe("code-sample-band-data", () => {
  it("exposes the three language tabs, in order", () => {
    expect(CODE_SAMPLES.map((s) => s.id)).toEqual(["curl", "python", "typescript"]);
  });

  it("every sample has a label and non-empty code", () => {
    for (const s of CODE_SAMPLES) {
      expect(s.label.length).toBeGreaterThan(0);
      expect(s.code.trim().length).toBeGreaterThan(0);
    }
  });

  it("getSampleById returns the matching sample", () => {
    expect(getSampleById("python")?.label).toBe("Python");
    expect(getSampleById("curl")?.id).toBe("curl");
  });

  it("getSampleById returns undefined for an unknown id", () => {
    expect(getSampleById("ruby")).toBeUndefined();
  });
});
