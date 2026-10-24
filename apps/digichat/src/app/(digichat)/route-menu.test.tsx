// @vitest-environment happy-dom
"use client";

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RouteMenu } from "./route-menu";

/**
 * Audit T1/T3: the root menu was a rounded card with a shadow, `bg-muted`
 * rows and muted-foreground labels — the shadcn default inside a zero-radius
 * ink/hair system. It is now a hairline command list.
 */
describe("RouteMenu", () => {
  it("keeps the three surfaces on hairline rows", () => {
    const { container } = render(<RouteMenu />);
    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(container.querySelectorAll(".app-menu-row")).toHaveLength(3);
    expect(container.innerHTML).not.toMatch(
      /rounded-|shadow-|bg-card|bg-muted|border-border/,
    );
  });

  it("names each surface with its destination copy", () => {
    render(<RouteMenu />);
    for (const title of ["Product chat", "Embed preview", "Skin catalog"]) {
      expect(screen.getByText(title)).toBeTruthy();
    }
  });
});
