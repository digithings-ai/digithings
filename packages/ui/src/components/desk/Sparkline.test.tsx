// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { Sparkline } from "./Sparkline";

afterEach(cleanup);

describe("Sparkline", () => {
  it("draws one hairline through the points it was given", () => {
    const { container } = render(<Sparkline values={[10, 12, 11, 15]} />);
    const line = container.querySelector("polyline");
    expect(line).toBeTruthy();
    expect(line?.getAttribute("points")?.split(" ")).toHaveLength(4);
    expect(line?.getAttribute("stroke")).toBe("currentColor");
    expect(line?.getAttribute("vector-effect")).toBe("non-scaling-stroke");
    expect(container.querySelector("svg")?.getAttribute("viewBox")).toBe("0 0 100 100");
  });

  it("summarises the real points for a screen reader", () => {
    render(<Sparkline values={[10, 15, 12]} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "sparkline, 3 points, 10 to 12, low 10, high 15",
    );
  });

  it("takes an explicit label and can be decorative", () => {
    const { container, rerender } = render(
      <Sparkline values={[1, 2]} label="portfolio nav, 30 days" />,
    );
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("portfolio nav, 30 days");

    rerender(<Sparkline values={[1, 2]} label="portfolio nav, 30 days" decorative />);
    const svg = container.querySelector("svg");
    expect(screen.queryByRole("img")).toBeNull();
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(svg?.getAttribute("aria-label")).toBeNull();
  });

  it("drops non-finite points instead of plotting them as zero", () => {
    const { container } = render(<Sparkline values={[1, null, Number.NaN, 3, undefined, 5]} />);
    expect(container.querySelector("polyline")?.getAttribute("points")?.split(" ")).toHaveLength(3);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("3 points");
  });

  it("says so when there is nothing to draw", () => {
    render(<Sparkline values={[4]} />);
    expect(screen.getByText("not enough points")).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("carries no motion, so reduced motion needs no special case", () => {
    const { container } = render(<Sparkline values={[1, 2, 3]} />);
    expect(container.innerHTML).not.toMatch(/animate-|transition|motion-/);
    expect(container.innerHTML).not.toMatch(/#[0-9a-f]{3,8}\b|rgba?\(/i);
  });
});
