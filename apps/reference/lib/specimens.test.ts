import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { ROUTES, SPECIMENS } from "./specimen-inventory";

const APP = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const REPO = path.resolve(APP, "../..");
const UI_INDEX = path.join(REPO, "packages/ui/src/ui/index.ts");

/** `export * from "./alert"` → `alert`. */
function kitUiModules(): string[] {
  const source = readFileSync(UI_INDEX, "utf8");
  return [...source.matchAll(/export \* from "\.\/([^"]+)";/g)].map((m) => m[1]).sort();
}

const MODULES = kitUiModules();

describe("kit specimen contract", () => {
  it("found the kit UI barrel", () => {
    expect(MODULES.length).toBeGreaterThan(0);
  });

  it("every /ui module has exactly one canonical specimen", () => {
    for (const part of MODULES) {
      expect(SPECIMENS[part], `no specimen for @digithings/ui/ui ${part}`).toBeDefined();
    }
  });

  it("has no stale specimen entries for removed kit modules", () => {
    const known = new Set(MODULES);
    for (const key of Object.keys(SPECIMENS)) {
      expect(known.has(key), `specimen entry "${key}" has no kit module`).toBe(true);
    }
  });

  it("every specimen file exists and references its marker", () => {
    for (const [part, entry] of Object.entries(SPECIMENS)) {
      const file = path.join(APP, entry.specimen);
      expect(existsSync(file), `${part}: ${entry.specimen}`).toBe(true);
      const source = readFileSync(file, "utf8");
      if (entry.marker) {
        expect(source, `${part} marker ${entry.marker} in ${entry.specimen}`).toContain(
          entry.marker,
        );
      }
    }
  });

  it("every specimen route is a real route", () => {
    const routes = new Set(ROUTES.map((r) => r.route));
    for (const entry of Object.values(SPECIMENS)) {
      expect(routes.has(entry.route), entry.route).toBe(true);
    }
  });

  it("each part has a single home (no specimen claims two parts' markers)", () => {
    // The map is keyed by module, so a part cannot have two homes unless two
    // modules point at different files with the same marker. Guard the parts
    // the consolidation explicitly singled out.
    const table = SPECIMENS.table.specimen;
    const source = readFileSync(path.join(APP, table), "utf8");
    expect(source).toContain("density=");
    expect(source).toContain("numeric");
    expect(source).toContain("TableRowHeader");
    expect(source).toContain("interactive");
  });

  it("the badge specimen demonstrates every tone", () => {
    const source = readFileSync(path.join(APP, SPECIMENS.badge.specimen), "utf8");
    for (const tone of ["neutral", "accent", "warn", "up", "down"]) {
      expect(source, `badge tone ${tone}`).toContain(`"${tone}"`);
    }
  });

  it("the select specimen uses the kit's SelectPopup composition", () => {
    const source = readFileSync(path.join(APP, SPECIMENS.select.specimen), "utf8");
    expect(source).toContain("SelectPopup");
  });
});
