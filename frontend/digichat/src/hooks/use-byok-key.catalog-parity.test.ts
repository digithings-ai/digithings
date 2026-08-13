import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { BYOK_PROVIDER_LIST, byokRequiresModel, type BYOKProvider } from "./use-byok-key";

type CatalogEntry = { id: string; requiresModel?: boolean };

function loadCatalog(): CatalogEntry[] {
  const path = resolve(process.cwd(), "../../config/byok-providers.json");
  return JSON.parse(readFileSync(path, "utf-8")) as CatalogEntry[];
}

describe("use-byok-key <-> config/byok-providers.json parity", () => {
  it("BYOK_PROVIDER_LIST contains exactly the catalog's provider ids", () => {
    const catalog = loadCatalog();
    const catalogIds = new Set(catalog.map((e) => e.id));
    const tsIds = new Set(BYOK_PROVIDER_LIST as readonly string[]);
    expect(tsIds).toEqual(catalogIds);
  });

  it("byokRequiresModel agrees with the catalog's requiresModel per provider", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(byokRequiresModel(entry.id as BYOKProvider)).toBe(Boolean(entry.requiresModel));
    }
  });
});
