// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import { meterTone } from "./digichat-meter-tone";
import { DigichatUsageMeter, usageBarShape } from "./digichat-usage-meter";

afterEach(() => {
  cleanup();
});

describe("usageBarShape", () => {
  it("gives the three free turns one cell each", () => {
    expect(usageBarShape(0, 3)).toEqual({ cells: 3, lit: 0 });
    expect(usageBarShape(1, 3)).toEqual({ cells: 3, lit: 1 });
    expect(usageBarShape(2, 3)).toEqual({ cells: 3, lit: 2 });
    expect(usageBarShape(3, 3)).toEqual({ cells: 3, lit: 3 });
  });

  it("fills the shared 25-cell grid proportionally after unlock", () => {
    expect(usageBarShape(0, 100)).toEqual({ cells: 25, lit: 0 });
    expect(usageBarShape(4, 100)).toEqual({ cells: 25, lit: 1 });
    expect(usageBarShape(50, 100)).toEqual({ cells: 25, lit: 13 });
    expect(usageBarShape(100, 100)).toEqual({ cells: 25, lit: 25 });
  });

  it("keeps a spent turn visible instead of rounding it away", () => {
    // 1/100 would round to 0 cells; an empty bar would read as "no turns
    // used" on a visitor who has already spent one.
    expect(usageBarShape(1, 100).lit).toBe(1);
  });

  it("stays one cell short until the budget is actually spent", () => {
    // 98/100 and 99/100 round to a full bar, but a turn is still left; a full
    // bar must mean "no turns left", so the last cell waits for 100/100.
    expect(usageBarShape(98, 100).lit).toBe(24);
    expect(usageBarShape(99, 100).lit).toBe(24);
    expect(usageBarShape(100, 100).lit).toBe(25);
  });

  it("clamps out-of-range counts and refuses a zero budget", () => {
    expect(usageBarShape(-2, 3)).toEqual({ cells: 3, lit: 0 });
    expect(usageBarShape(9, 3)).toEqual({ cells: 3, lit: 3 });
    expect(usageBarShape(140, 100)).toEqual({ cells: 25, lit: 25 });
    expect(usageBarShape(2, 0)).toEqual({ cells: 0, lit: 0 });
  });
});

describe("meterTone", () => {
  it("moves through the scale as the fill grows", () => {
    expect(meterTone(0)).toBe("");
    expect(meterTone(0.59)).toBe("");
    expect(meterTone(0.6)).toBe("is-warn");
    expect(meterTone(0.79)).toBe("is-warn");
    expect(meterTone(0.8)).toBe("is-hot");
    expect(meterTone(0.89)).toBe("is-hot");
    expect(meterTone(0.9)).toBe("is-critical");
    expect(meterTone(1)).toBe("is-critical");
  });

  it("stays untoned without a denominator", () => {
    expect(meterTone(Number.NaN)).toBe("");
    // An infinite ratio is not "full": there is no window to be a fraction of.
    expect(meterTone(Number.POSITIVE_INFINITY)).toBe("");
    expect(meterTone(-1)).toBe("");
  });
});

describe("DigichatUsageMeter", () => {
  it("draws three cells for the free budget and names the turns left", () => {
    const { container } = render(
      <DigichatUsageMeter usage={{ used: 2, limit: 3 }} />,
    );
    expect(container.querySelectorAll(".aui-context-bar-cell")).toHaveLength(3);
    expect(container.querySelectorAll(".aui-context-bar-cell.is-usage")).toHaveLength(2);
    expect(
      container.querySelector('[data-testid="embed-usage-meter"]')?.getAttribute("aria-label"),
    ).toBe("Turns: 1 of 3 left");
  });

  it("carries the tone on the bar and the wrapper", () => {
    const { container } = render(
      <DigichatUsageMeter usage={{ used: 2, limit: 3 }} />,
    );
    expect(container.querySelector(".aui-usage-meter-wrap.is-warn")).not.toBeNull();
    expect(container.querySelector(".aui-usage-meter.is-warn")).not.toBeNull();
  });

  it("shows turns left and used in the hover card", () => {
    const { container } = render(
      <DigichatUsageMeter usage={{ used: 4, limit: 100 }} />,
    );
    const card = container.querySelector(".aui-context-card");
    expect(card?.textContent).toContain("Turns left");
    expect(card?.textContent).toContain("96");
    expect(card?.textContent).toContain("4 / 100");
  });

  it("renders nothing for a zero budget", () => {
    const { container } = render(
      <DigichatUsageMeter usage={{ used: 0, limit: 0 }} />,
    );
    expect(container.firstElementChild).toBeNull();
  });
});
