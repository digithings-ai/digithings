import { describe, expect, it } from "vitest";
import { stepSelectableForTests as step } from "./embed-composer-menu";

const rows = [
  { id: "auto" },
  { id: "h1", heading: true },
  { id: "a" },
  { id: "b" },
  { id: "h2", heading: true },
  { id: "c" },
] as never[];

describe("menu cursor over provider headings", () => {
  it("steps from a heading to the nearest row in that direction", () => {
    expect(step(1, 1, rows)).toBe(2);
    expect(step(4, 1, rows)).toBe(5);
    expect(step(4, -1, rows)).toBe(3);
    expect(step(1, -1, rows)).toBe(0);
  });

  it("steps between selectable rows and skips headings", () => {
    expect(step(0, 1, rows)).toBe(2);
    expect(step(3, 1, rows)).toBe(5);
    expect(step(2, -1, rows)).toBe(0);
  });
});
