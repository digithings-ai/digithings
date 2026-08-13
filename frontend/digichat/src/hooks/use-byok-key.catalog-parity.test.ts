import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  BYOK_PROVIDER_LIST,
  byokModelPresets,
  byokRequiresModel,
  validateBYOKKey,
  type BYOKProvider,
} from "./use-byok-key";

type CatalogEntry = {
  id: string;
  requiresModel?: boolean;
  keyPrefix: string;
  fallbackModels: string[];
};

function loadCatalog(): CatalogEntry[] {
  const path = resolve(process.cwd(), "../../config/byok-providers.json");
  return JSON.parse(readFileSync(path, "utf-8")) as CatalogEntry[];
}

/** Never starts with any real provider's keyPrefix (sk-or-, sk-, sk-ant-, AI, xai-). */
const KEY_NOT_MATCHING_ANY_PREFIX = "not-a-real-provider-key-000";

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

  // Nothing has drifted yet, but nothing asserted it either: keyPrefix and
  // fallbackModels are read from this catalog by no runtime code (only
  // id/baseUrl/requiresModel feed digigraph/src/digigraph/llm_auth.py's
  // loader) — they exist purely to stay in parity with the hand-written
  // copies in use-byok-key.ts (validateBYOKKey, byokModelPresets) and
  // api/byok/test/route.ts's inline prefix checks. Without this test, either
  // copy could silently drift from the catalog with nothing to catch it.
  it("validateBYOKKey rejects a key that doesn't start with the catalog's keyPrefix for that provider", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(KEY_NOT_MATCHING_ANY_PREFIX.startsWith(entry.keyPrefix)).toBe(false);
      const result = validateBYOKKey(KEY_NOT_MATCHING_ANY_PREFIX, entry.id as BYOKProvider);
      expect(result).not.toBeNull();
    }
  });

  it("byokModelPresets(provider) matches the catalog's fallbackModels exactly", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(byokModelPresets(entry.id as BYOKProvider)).toEqual(entry.fallbackModels);
    }
  });
});
