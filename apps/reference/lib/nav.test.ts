import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { LAB_NAV, PRIMARY_NAV } from "./nav";
import { ROUTES } from "./specimen-inventory";

const APP = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const routes = new Set(ROUTES.map((r) => r.route));

describe("navigation inventory", () => {
  it("every nav href resolves to a real route", () => {
    for (const item of [...PRIMARY_NAV, ...LAB_NAV]) {
      expect(routes.has(item.href), item.href).toBe(true);
      expect(item.label.length).toBeGreaterThan(0);
      expect(item.blurb.length).toBeGreaterThan(0);
    }
  });

  it("every route is reachable from the nav (primary or lab)", () => {
    const listed = new Set([...PRIMARY_NAV, ...LAB_NAV].map((i) => i.href));
    for (const entry of ROUTES) {
      expect(listed.has(entry.route), `${entry.route} is not in the nav`).toBe(true);
    }
  });

  it("has no duplicate hrefs across the two groups", () => {
    const hrefs = [...PRIMARY_NAV, ...LAB_NAV].map((i) => i.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("keeps reference-only surfaces off the primary row", () => {
    const primary = new Set(PRIMARY_NAV.map((i) => i.href));
    expect(primary.has("/brand")).toBe(false);
    expect(primary.has("/iterate")).toBe(false);
    expect(LAB_NAV.map((i) => i.href).sort()).toEqual(["/brand", "/iterate"]);
  });

  it("site-nav and contents-overview read the shared nav data", () => {
    for (const rel of ["components/site-nav.tsx", "components/contents-overview.tsx"]) {
      const source = readFileSync(path.join(APP, rel), "utf8");
      expect(source, rel).toContain("@/lib/nav");
    }
  });
});
