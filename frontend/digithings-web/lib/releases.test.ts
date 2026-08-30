import { describe, expect, it } from "vitest";
import releases from "../../digiweb/design/releases.json";

describe("tagged frontend releases feed", () => {
  it("is a non-empty list of real GitHub release rows", () => {
    expect(releases.length).toBeGreaterThan(0);
    for (const row of releases) {
      expect(row.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(row.version.length).toBeGreaterThan(0);
      expect(row.title.length).toBeGreaterThan(0);
      expect(row.href).toMatch(/^https:\/\/github\.com\/digithings-ai\/digithings\/releases\/tag\//);
      expect(["fix", "release"]).toContain(row.tag);
      expect(row.product.length).toBeGreaterThan(0);
    }
  });

  it("does not ship the example changelog placeholders", () => {
    const blob = JSON.stringify(releases);
    expect(blob).not.toContain("Example release entry");
    expect(blob).not.toContain("v7.2");
  });
});
