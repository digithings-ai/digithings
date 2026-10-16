import { existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ROUTES } from "./specimen-inventory";

const APP = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = path.join(dir, entry);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

/** `/` + the non-group path segments of a `page.tsx`'s directory. */
function routeFor(pageFile: string): string {
  const rel = path.relative(path.join(APP, "app"), path.dirname(pageFile));
  const segments = rel
    .split(path.sep)
    .filter((s) => s.length > 0 && !(s.startsWith("(") && s.endsWith(")")));
  return `/${segments.join("/")}`;
}

describe("route inventory", () => {
  const pageFiles = walk(path.join(APP, "app")).filter((f) => f.endsWith("page.tsx"));
  const discovered = pageFiles.map(routeFor).sort();

  it("every declared route exists on disk", () => {
    for (const entry of ROUTES) {
      const full = path.join(APP, entry.page);
      expect(existsSync(full), `${entry.route} → ${entry.page}`).toBe(true);
    }
  });

  it("the filesystem route set matches the inventory exactly", () => {
    expect(discovered).toEqual(ROUTES.map((r) => r.route).sort());
  });

  it("no retired routes remain", () => {
    // `/ui` and `/tearsheet` folded into /controls and /finance.
    expect(discovered).not.toContain("/ui");
    expect(discovered).not.toContain("/tearsheet");
  });

  it("every route is a single static page (no dynamic segments)", () => {
    for (const file of pageFiles) {
      expect(path.relative(APP, file)).not.toMatch(/\[[^\]]+\]/);
    }
  });
});
