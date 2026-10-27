import { describe, expect, it } from "vitest";
import { isSamplingRate, keepTrace, LAUNCH_SAMPLING_RATE, traceIdFraction } from "./sampling";

const TRACE = "0af7651916cd43dd8448eb211c80319c";

describe("launch sampling", () => {
  it("is 100% at launch, as ADR-0036 §2 fixes it", () => {
    expect(LAUNCH_SAMPLING_RATE).toBe(1);
  });
});

describe("isSamplingRate", () => {
  it("accepts a finite number in [0, 1]", () => {
    expect(isSamplingRate(0)).toBe(true);
    expect(isSamplingRate(0.25)).toBe(true);
    expect(isSamplingRate(1)).toBe(true);
  });

  it("rejects everything else", () => {
    expect(isSamplingRate(-0.1)).toBe(false);
    expect(isSamplingRate(1.1)).toBe(false);
    expect(isSamplingRate(Number.NaN)).toBe(false);
    expect(isSamplingRate("1")).toBe(false);
    expect(isSamplingRate(undefined)).toBe(false);
  });
});

describe("keepTrace", () => {
  it("keeps every trace at a rate of 1, including the id at the top of the range", () => {
    expect(keepTrace("ffffffffffffffffffffffffffffffff", 1)).toBe(true);
    expect(keepTrace(TRACE, 1)).toBe(true);
  });

  it("keeps nothing at a rate of 0", () => {
    expect(keepTrace("00000000000000000000000000000000", 0)).toBe(false);
    expect(keepTrace(TRACE, 0)).toBe(false);
  });

  it("is deterministic: the same trace id always gets the same answer", () => {
    const first = keepTrace(TRACE, 0.5);
    for (let i = 0; i < 50; i += 1) expect(keepTrace(TRACE, 0.5)).toBe(first);
  });

  it("keeps about the requested fraction of many trace ids", () => {
    let kept = 0;
    const total = 4000;
    for (let i = 0; i < total; i += 1) {
      // The draw reads the last four bytes, so the fixture must vary them: a
      // counter in the outmost bits would test nothing.
      const mixed = Math.imul(i + 1, 0x9e3779b1) >>> 0;
      const traceId = mixed.toString(16).padStart(8, "0").repeat(4);
      if (keepTrace(traceId, 0.25)) kept += 1;
    }
    // 4000 uniform ids at 25%: 1000 expected, and a binomial sd of ~27 makes
    // ±150 an extremely loose bound that still fails a wrong threshold.
    expect(kept).toBeGreaterThan(850);
    expect(kept).toBeLessThan(1150);
  });

  it("drops everything for an invalid rate rather than guessing", () => {
    expect(keepTrace(TRACE, Number.NaN)).toBe(false);
    expect(keepTrace(TRACE, 2)).toBe(false);
  });
});

describe("traceIdFraction", () => {
  it("is in [0, 1)", () => {
    expect(traceIdFraction(TRACE)).toBeGreaterThanOrEqual(0);
    expect(traceIdFraction(TRACE)).toBeLessThan(1);
  });

  it("reads the last four bytes, so a shared prefix does not collapse the draw", () => {
    const a = traceIdFraction("0".repeat(28) + "00000001");
    const b = traceIdFraction("0".repeat(28) + "80000000");
    expect(a).toBeCloseTo(1 / 0x1_0000_0000, 12);
    expect(b).toBeCloseTo(0.5, 6);
  });
});
