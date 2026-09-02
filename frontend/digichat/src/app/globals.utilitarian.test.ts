import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = join(here, "..");
const globalsPath = join(here, "globals.css");
const layoutPath = join(here, "layout.tsx");
const embedClientPath = join(here, "embed/embed-client.tsx");

function read(path: string): string {
  return readFileSync(path, "utf8");
}

function walkTsx(dir: string, out: string[] = []): string[] {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, ent.name);
    if (ent.isDirectory()) {
      if (ent.name === "node_modules") continue;
      walkTsx(p, out);
    } else if (ent.name.endsWith(".tsx") && !ent.name.includes(".test.")) {
      out.push(p);
    }
  }
  return out;
}

/** Chrome radius utilities (pills/soft cards). True circles (`rounded-full`) stay. */
const CHROME_RADIUS = /\brounded-(?:sm|md|lg|xl|2xl|3xl|4xl)\b/;

describe("utilitarian-terminal v0.1 — digichat local fights", () => {
  const css = read(globalsPath);

  it("pins shadcn --radius to 0 so Tailwind rounded-* inherit zero chrome", () => {
    expect(css).not.toMatch(/--radius:\s*0\.625rem/);
    expect(css).toMatch(/:root\s*\{[^}]*--radius:\s*0\s*;/s);
    expect(css).toMatch(/--radius-sm:\s*0\s*;/);
    expect(css).toMatch(/--radius-md:\s*0\s*;/);
    expect(css).toMatch(/--radius-lg:\s*0\s*;/);
  });

  it("maps shadcn --primary to ink/paper, not rose livery fill", () => {
    expect(css).not.toMatch(/--primary:\s*var\(--accent-digichat\)/);
    expect(css).toMatch(/--primary:\s*var\(--ink\)/);
    expect(css).toMatch(/--primary-foreground:\s*var\(--bg\)/);
    // Rose stays on focus/live/identity slots.
    expect(css).toMatch(/--ring:\s*var\(--accent-digichat\)/);
  });

  it("defaults type to the loaded Geist Mono stack, not Inter/sans display", () => {
    expect(css).toMatch(/--font-heading:\s*var\(--font-mono\)/);
    expect(css).toMatch(
      /--font-sans:\s*var\(--font-geist-mono\),\s*ui-monospace,\s*monospace/,
    );
    expect(css).toMatch(/--font-display:\s*var\(--font-mono\)/);
    expect(css).toMatch(/--font-family:\s*var\(--font-mono\)/);
    expect(css).not.toMatch(/--font-sans:\s*var\(--font-geist-sans\)/);
  });

  it("does not ship pill radius on local chrome (999px)", () => {
    expect(css).not.toMatch(/border-radius:\s*999px/);
  });

  it("overrides imported .dc-send to an ink/paper rect", () => {
    expect(css).toMatch(/\.dc-send\s*\{[^}]*border-radius:\s*0/s);
    expect(css).toMatch(/\.dc-send\s*\{[^}]*background:\s*var\(--ink\)/s);
    expect(css).toMatch(/\.dc-send\s*\{[^}]*color:\s*var\(--bg\)/s);
  });

  it("does not put font-sans on the document body", () => {
    const layout = read(layoutPath);
    expect(layout).not.toMatch(/<body[^>]*font-sans/);
    expect(layout).toMatch(/<body[^>]*font-mono/);
  });

  it("does not fill the embed BYOK CTA with module accent", () => {
    const embed = read(embedClientPath);
    expect(embed).not.toMatch(
      /backgroundColor:\s*["']var\(--accent\)["']/,
    );
  });

  it("strips shadcn rounded-* chrome utilities (keeps rounded-full geometry)", () => {
    const offenders: string[] = [];
    for (const file of walkTsx(srcRoot)) {
      const text = read(file);
      for (const [i, line] of text.split("\n").entries()) {
        if (!CHROME_RADIUS.test(line)) continue;
        offenders.push(`${relative(srcRoot, file)}:${i + 1}: ${line.trim()}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
