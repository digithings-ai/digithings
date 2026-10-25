import { describe, expect, it } from "vitest";
import { kitIndex, uiComposites, uiPrimitives } from "./kit-index";

describe("kit index", () => {
  it("reads every UI primitive from the barrel", () => {
    const primitives = uiPrimitives();
    expect(primitives.length).toBeGreaterThanOrEqual(30);
    expect(primitives.map((entry) => entry.name)).toContain("button");
    expect(primitives.map((entry) => entry.name)).toContain("select");
    for (const entry of primitives) {
      expect(entry.from).toBe("@digithings/ui/ui");
      expect(entry.module).toBe(`ui/${entry.name}`);
    }
  });

  it("reads the composite modules from the package barrel", () => {
    const composites = uiComposites();
    expect(composites.length).toBeGreaterThanOrEqual(40);
    expect(composites.map((entry) => entry.module)).toContain("components/ThemeProvider");
    expect(new Set(composites.map((entry) => entry.module)).size).toBe(composites.length);
    for (const entry of composites) {
      expect(entry.from).toBe("@digithings/ui");
      expect(entry.name.length).toBeGreaterThan(0);
    }
  });

  it("returns both families for the page", () => {
    const index = kitIndex();
    expect(index.primitives.length).toBeGreaterThan(0);
    expect(index.composites.length).toBeGreaterThan(0);
  });
});
