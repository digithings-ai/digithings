import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The boot overlay mounts on every skin, so its styles must ship with the
// loaders themselves. Imported only by the digichat skin, the overlay rendered
// unpositioned (80px tall at the top, wordmark clipped) on the other skins.
describe("boot loader styles ship with the loaders", () => {
  for (const file of ["boot-lab.tsx", "DigichatBootLoader.tsx"]) {
    it(file, () => {
      const src = readFileSync(join(__dirname, file), "utf8");
      expect(src).toContain('import "../../styles/digichat-boot-loader.css";');
    });
  }
  it("the overlay covers its host", () => {
    const css = readFileSync(join(__dirname, "../../styles/digichat-boot-loader.css"), "utf8");
    expect(css).toMatch(/\.dboot-overlay \{\s*position: absolute;\s*inset: 0;/);
  });
});
