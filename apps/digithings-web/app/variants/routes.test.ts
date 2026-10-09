import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const pagePath = fileURLToPath(new URL("./page.tsx", import.meta.url));
const variantsDir = dirname(pagePath);

describe("variant routes", () => {
  it("gives every index link a real /variants page", () => {
    const src = readFileSync(pagePath, "utf8");
    expect(existsSync(join(variantsDir, "page.tsx"))).toBe(true);
    expect(existsSync(join(variantsDir, "..", "_variants-pages"))).toBe(false);

    const slugs = [...src.matchAll(/slug: "([^"]+)"/g)].map((match) => match[1]);
    expect(slugs.length).toBeGreaterThan(0);
    for (const slug of slugs) {
      expect(src).toContain("`/variants/${v.slug}`");
      expect(existsSync(join(variantsDir, slug, "page.tsx"))).toBe(true);
    }
    expect(src).toContain('href="/variants/mixed"');
    expect(src).toContain('href="/variants/command-bar"');
  });
});
