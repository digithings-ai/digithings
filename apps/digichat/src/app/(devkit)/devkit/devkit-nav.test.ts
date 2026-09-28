import { describe, expect, it } from "vitest";
import { visibleGroupFromEntries } from "./devkit-editors";

describe("visibleGroupFromEntries", () => {
  it("returns null with no entries", () => {
    expect(visibleGroupFromEntries([])).toBe(null);
  });
  it("picks the foremost group", () => {
    expect(
      visibleGroupFromEntries([
        { id: "basics", top: -120 },
        { id: "appearance", top: 40 },
        { id: "advanced", top: 600 },
      ]),
    ).toBe("basics");
  });
});
