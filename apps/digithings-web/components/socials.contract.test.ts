import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function load(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
}

describe("digithings.ai socials import", () => {
  it("puts SocialRow on the contact band, not a live /brand kit page", () => {
    // The landing page is composed in LandingPage.tsx; app/page.tsx renders it.
    // The contract is about the band, so it follows the band.
    const home = load("../components/landing/LandingPage.tsx");
    expect(home).toContain("SocialRow");
    // The contact band's anchor, not its marketing copy: #contact is the stable
    // contract (the pricing CTAs and the section rail link to it), and the prose there is
    // free to be rewritten. The sentence this used to pin was replaced in the
    // document-grammar rebuild (D1, #4429).
    expect(home).toContain('id="contact"');
    expect(home).not.toMatch(/Discord/i);
    const liveBrand = fileURLToPath(new URL("../app/brand/page.tsx", import.meta.url));
    expect(existsSync(liveBrand)).toBe(false);
  });

  it("mounts the same primitive in the shared site footer", () => {
    const footer = load("./DtFooter.tsx");
    expect(footer).toContain("<SocialRow");
    expect(footer).toContain("<Footer");
    expect(footer).not.toMatch(/Discord/i);
  });
});
