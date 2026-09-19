import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const globalsPath = join(here, "globals.css");
const layoutPath = join(here, "layout.tsx");
const embedClientPath = join(here, "embed/embed-client.tsx");

function read(path: string): string {
  return readFileSync(path, "utf8");
}

/**
 * Catalog skins keep Inter / IBM Plex on product globals (see product-isolation).
 * `chrome.skin: digichat` loads Geist Mono as `--font-geist-mono` and consumes
 * gallery `chatbot.css` — not the 1.5 CLI session sheets.
 */
describe("product chrome vs 1.5 utilitarian-terminal", () => {
  const css = read(globalsPath);

  it("keeps stock shadcn radius/type on product globals, not CLI ink/paper", () => {
    expect(css).toMatch(/--radius:\s*0\.625rem/);
    expect(css).toMatch(/--font-sans:\s*var\(--font-inter\)/);
    expect(css).not.toMatch(
      /--font-sans:\s*var\(--font-geist-mono\),\s*ui-monospace,\s*monospace/,
    );
    expect(css).not.toMatch(/--primary:\s*var\(--ink\)/);
  });

  it("does not put Geist Mono on the document body", () => {
    const layout = read(layoutPath);
    expect(layout).not.toMatch(/<body[^>]*font-mono/);
    expect(layout).toMatch(/inter\.className/);
    expect(layout).toMatch(/geistMono\.variable/);
    expect(layout).not.toMatch(/geistMono\.className/);
  });

  it("does not fill the embed BYOK CTA with module accent", () => {
    const embed = read(embedClientPath);
    expect(embed).not.toMatch(/backgroundColor:\s*["']var\(--accent\)["']/);
  });
});
