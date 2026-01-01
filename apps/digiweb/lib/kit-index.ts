import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The kit index — what `@digithings/ui` actually exports, read from source.
 *
 * The components page does not keep a second hand-written catalogue: it parses
 * the package's own barrel files, so a new primitive or composite appears on
 * the page without an edit here. `lib/kit-index.test.ts` proves the parser
 * still finds a plausible index, so a format change cannot empty the page
 * silently.
 */

const HERE = path.dirname(fileURLToPath(import.meta.url));

/** Repo root from `apps/digiweb/lib` (three levels up). */
export const REPO_ROOT = path.resolve(HERE, "..", "..", "..");

export type KitEntry = {
  /** The exported symbol or primitive name. */
  name: string;
  /** The module path inside `@digithings/ui`. */
  module: string;
  /** The import specifier a consumer writes. */
  from: string;
};

function readSource(relative: string): string {
  return readFileSync(path.join(REPO_ROOT, relative), "utf8");
}

/** `export * from "./button"` in `src/ui/index.ts` → the 34 primitives. */
export function uiPrimitives(): KitEntry[] {
  const source = readSource("packages/ui/src/ui/index.ts");
  return [...source.matchAll(/export \* from "\.\/([^"]+)"/g)].map((match) => ({
    name: match[1],
    module: `ui/${match[1]}`,
    from: "@digithings/ui/ui",
  }));
}

/** Every `from "./…"` in `src/index.ts` → the composite modules. */
export function uiComposites(): KitEntry[] {
  const source = readSource("packages/ui/src/index.ts");
  const modules = new Set<string>();
  for (const match of source.matchAll(/from "\.\/([^"]+)"/g)) {
    modules.add(match[1]);
  }
  return [...modules].sort().map((module) => ({
    name: module.split("/").pop() ?? module,
    module,
    from: "@digithings/ui",
  }));
}

/** One read of both barrels, for the page. */
export function kitIndex(): { primitives: KitEntry[]; composites: KitEntry[] } {
  return { primitives: uiPrimitives(), composites: uiComposites() };
}
