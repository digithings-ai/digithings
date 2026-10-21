import { describe, expect, it } from "vitest";

import {
  CONTEXT_BAR_CELLS,
  computeContextShares,
} from "./digichat-context-meter-shares";

const WINDOW = 1_048_576;

const sum = (values: number[]): number =>
  values.reduce((total, value) => total + value, 0);

describe("computeContextShares", () => {
  it("keeps every share inside the turn when the tool estimate exceeds the prompt total", () => {
    const shares = computeContextShares({
      input: 1000,
      userChars: 0,
      // 10 tools at the flat per-tool allowance is 2200 tokens, above the
      // reported total of 1000.
      toolCount: 10,
      window: WINDOW,
    });

    expect(shares.toolTokens).toBe(1000);
    expect(sum([shares.systemTokens, shares.toolTokens, shares.userTokens])).toBe(
      1000,
    );
    expect(shares.toolPct).toBeLessThanOrEqual(100);
    expect(shares.systemPct + shares.toolPct + shares.userPct).toBe(100);
  });

  it("splits a normal turn into its three parts", () => {
    const shares = computeContextShares({
      input: 1000,
      userChars: 400, // 100 tokens of user text
      toolCount: 2, // 440 tokens of schema estimate
      window: WINDOW,
    });

    expect(shares.userTokens).toBe(100);
    expect(shares.toolTokens).toBe(440);
    expect(shares.systemTokens).toBe(460);
    expect(sum([shares.systemTokens, shares.toolTokens, shares.userTokens])).toBe(
      1000,
    );
    expect(shares.systemPct + shares.toolPct + shares.userPct).toBe(100);
    expect(shares.userPct).toBe(10);
    expect(shares.toolPct).toBe(44);
    expect(shares.systemPct).toBe(46);
  });

  it("clamps user text that is larger than the prompt total", () => {
    const shares = computeContextShares({
      input: 100,
      userChars: 4000, // 1000 tokens of user text
      toolCount: 3,
      window: WINDOW,
    });

    expect(shares.userTokens).toBe(100);
    expect(shares.toolTokens).toBe(0);
    expect(shares.systemTokens).toBe(0);
    expect(sum([shares.systemTokens, shares.toolTokens, shares.userTokens])).toBe(
      100,
    );
    expect(shares.userPct).toBe(100);
    expect(shares.systemPct + shares.toolPct + shares.userPct).toBe(100);
  });

  it("sums the shares to exactly 100 when independent rounding would not", () => {
    // 3 user tokens, 5 tool tokens, 0 system tokens: the exact shares are
    // 37.5% and 62.5%, so rounding each one gives 38 and 63.
    const shares = computeContextShares({
      input: 8,
      userChars: 12,
      toolCount: 1,
      window: WINDOW,
    });

    expect(shares.userTokens).toBe(3);
    expect(shares.toolTokens).toBe(5);
    expect(shares.systemTokens).toBe(0);
    expect(shares.userPct).toBe(38);
    expect(shares.toolPct).toBe(62);
    expect(shares.systemPct).toBe(0);
    expect(shares.systemPct + shares.toolPct + shares.userPct).toBe(100);
  });

  it("reports nothing while no turn has reported usage", () => {
    const shares = computeContextShares({
      input: 0,
      userChars: 800,
      toolCount: 4,
      window: WINDOW,
    });

    expect(shares.systemTokens).toBe(0);
    expect(shares.toolTokens).toBe(0);
    expect(shares.userTokens).toBe(0);
    expect(shares.systemPct).toBe(0);
    expect(shares.toolPct).toBe(0);
    expect(shares.userPct).toBe(0);
    expect(shares.usedCells).toBe(0);
  });

  it("keeps the shares in range for every tool count against one total", () => {
    for (let toolCount = 0; toolCount <= 50; toolCount += 1) {
      const shares = computeContextShares({
        input: 4096,
        userChars: 1200,
        toolCount,
        window: WINDOW,
      });

      const tokenTotal = sum([
        shares.systemTokens,
        shares.toolTokens,
        shares.userTokens,
      ]);
      expect(tokenTotal).toBe(4096);

      for (const pct of [
        shares.systemPct,
        shares.toolPct,
        shares.userPct,
      ]) {
        expect(pct).toBeGreaterThanOrEqual(0);
        expect(pct).toBeLessThanOrEqual(100);
      }
      expect(shares.systemPct + shares.toolPct + shares.userPct).toBe(100);
    }
  });

  it("fills the used bar span with the three shares", () => {
    const shares = computeContextShares({
      input: 1000,
      userChars: 400,
      toolCount: 2,
      window: WINDOW,
    });

    expect(shares.usedCells).toBeLessThanOrEqual(CONTEXT_BAR_CELLS);
    expect(
      sum([shares.systemCells, shares.toolCells, shares.userCells]),
    ).toBe(shares.usedCells);
  });
});
