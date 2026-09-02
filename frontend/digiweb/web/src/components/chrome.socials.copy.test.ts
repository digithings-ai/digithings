/**
 * Chrome family copy: socials are a dedicated reference, not a fake Connect
 * column. Footer stays utility columns + colophon. Discord does not exist.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const reference = join(here, "../../../reference");

function load(rel: string): string {
  return readFileSync(join(reference, rel), "utf8");
}

describe("FooterReference copy", () => {
  it("does not advertise Discord or a fake Connect column", () => {
    const src = load("components/footer-reference.tsx");
    expect(src).not.toMatch(/Discord/i);
    expect(src).not.toMatch(/title:\s*"Connect"/);
    expect(src).toContain('title: "Product"');
    expect(src).toContain('title: "Company"');
    expect(src).toContain('title: "Resources"');
  });
});

describe("Chrome page socials reference", () => {
  it("mounts SocialsReference after ModuleCardReference and before FooterReference", () => {
    const src = load("app/chrome/page.tsx");
    expect(src).toContain('import { SocialsReference } from "@/components/socials-reference"');
    const moduleIdx = src.indexOf("<ModuleCardReference />");
    const socialsIdx = src.indexOf("<SocialsReference />");
    const footerIdx = src.indexOf("<FooterReference />");
    expect(moduleIdx).toBeGreaterThan(-1);
    expect(socialsIdx).toBeGreaterThan(moduleIdx);
    expect(footerIdx).toBeGreaterThan(socialsIdx);
  });

  it("specimens the shared SocialRow primitive with live interactive links", () => {
    const src = load("components/socials-reference.tsx");
    expect(src).toContain("from \"@digithings/web\"");
    expect(src).toContain("<SocialRow");
    expect(src).toContain('{"// socials"}');
    expect(src).not.toMatch(/Discord/i);
    expect(src).not.toMatch(/\bOlympus\b/);
    expect(src).not.toMatch(/\bAtlas\b/);
    expect(src).not.toMatch(/\bHermes\b/);
    expect(src).not.toMatch(/\bKairos\b/);
  });
});
