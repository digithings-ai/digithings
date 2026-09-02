import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function load(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

describe("digithings.ai socials import", () => {
  it("puts SocialRow on the contact band and the brand kit page", () => {
    const home = load("../app/page.tsx");
    const brand = load("../app/brand/page.tsx");
    expect(home).toContain("SocialRow");
    expect(home).toContain("Questions, enterprise, or partnership");
    expect(brand).toContain("SocialRow");
    expect(home).not.toMatch(/Discord/i);
    expect(brand).not.toMatch(/Discord/i);
  });

  it("mounts the same primitive in the shared site footer", () => {
    const footer = load("./DtFooter.tsx");
    expect(footer).toContain("<SocialRow");
    expect(footer).toContain("<Footer");
    expect(footer).not.toMatch(/Discord/i);
  });
});
