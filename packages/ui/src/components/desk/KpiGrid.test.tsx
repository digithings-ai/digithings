// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { KpiGrid } from "./KpiGrid";

afterEach(cleanup);

describe("KpiGrid", () => {
  it("pairs every figure with its label in one definition list", () => {
    render(
      <KpiGrid
        items={[
          { label: "nav", value: "$1,204,338" },
          { label: "day p&l", value: "+1.84%", tone: "pos" },
          { label: "drawdown", value: "-6.2%", tone: "neg", note: "peak 2026-08-14" },
        ]}
      />,
    );
    const terms = screen.getAllByRole("term");
    expect(terms.map((node) => node.textContent)).toEqual(["nav", "day p&l", "drawdown"]);

    const values = screen.getAllByRole("definition");
    expect(values[0].textContent).toBe("$1,204,338");
    expect(values[1].textContent).toBe("+1.84%");
    expect(values[2].textContent).toContain("-6.2%");
    expect(values[2].textContent).toContain("peak 2026-08-14");
  });

  it("tablulates the figures and wears the money colours only on tone", () => {
    render(
      <KpiGrid
        items={[
          { label: "nav", value: "$1,204,338" },
          { label: "day", value: "+1.84%", tone: "pos" },
          { label: "dd", value: "-6.2%", tone: "neg" },
        ]}
      />,
    );
    const [nav, day, dd] = screen.getAllByRole("definition");
    for (const cell of [nav, day, dd]) {
      expect(cell.className).toContain("[font-variant-numeric:tabular-nums]");
    }
    expect(day.className).toContain("text-up");
    expect(dd.className).toContain("text-down");
    expect(nav.className).not.toContain("text-up");
    expect(nav.className).not.toContain("text-down");
  });

  it("renders the missing mark instead of inventing a zero", () => {
    render(
      <KpiGrid
        items={[
          { label: "nav", value: null },
          { label: "day", value: undefined },
          { label: "dd", value: "" },
          { label: "sharpe", value: Number.NaN },
        ]}
      />,
    );
    const values = screen.getAllByRole("definition");
    expect(values.map((node) => node.getAttribute("data-state"))).toEqual([
      "missing",
      "missing",
      "missing",
      "missing",
    ]);
    for (const cell of values) {
      expect(cell.textContent).toBe("—");
    }
    expect(screen.queryByText("0")).toBeNull();
  });

  it("names a glyph figure for assistive tech", () => {
    render(<KpiGrid items={[{ label: "live", value: "●", valueLabel: "live feed connected" }]} />);
    expect(screen.getByRole("definition").getAttribute("aria-label")).toBe("live feed connected");
  });

  it("carries no motion, so reduced motion needs no special case", () => {
    const { container } = render(<KpiGrid items={[{ label: "nav", value: "$1" }]} />);
    expect(container.innerHTML).not.toMatch(/animate-|transition|motion-/);
  });
});
