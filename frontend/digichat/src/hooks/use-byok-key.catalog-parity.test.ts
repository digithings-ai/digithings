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

  // Nothing has drifted yet, but nothing asserted it either. No digichat runtime
  // code reads this JSON: the prefixes are re-declared in lib/byok-providers.ts's
  // own CATALOG, and the model lists in use-byok-key.ts's byokModelPresets. Those
  // two literals are the hand-written copies this file pins — every prefix check
  // in the app funnels through byokKeyPrefixError (validateBYOKKey delegates to it
  // at use-byok-key.ts:230, and api/byok/test/route.ts imports and calls it), so
  // there is exactly one prefix implementation and it reads the TS copy.
  // fallbackModels has a second consumer outside this app:
  // digigraph/src/digigraph/llm_auth.py names each entry's first model as the
  // remediation example in byok_default_model_refusal. So drift here is now
  // user-visible in a way it was not before — digigraph would tell a caller to
  // send a model this UI never offers.
  it("validateBYOKKey rejects a key that doesn't start with the catalog's keyPrefix for that provider", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(KEY_NOT_MATCHING_ANY_PREFIX.startsWith(entry.keyPrefix)).toBe(false);
      const result = validateBYOKKey(KEY_NOT_MATCHING_ANY_PREFIX, entry.id as BYOKProvider);
      expect(result).not.toBeNull();
    }
  });

  // The test above only proves the negative direction (a key matching NO
  // prefix is rejected) — it can't detect the catalog's keyPrefix drifting
  // to a value validateBYOKKey doesn't actually check (e.g. catalog says
  // "sk-anthropic-" while validateBYOKKey still checks "sk-ant-": the
  // negative-only test above still passes, since the sentinel key matches
  // neither). This test closes that gap: a key built from exactly the
  // catalog's own keyPrefix must be ACCEPTED by validateBYOKKey.
  it("validateBYOKKey accepts a key built from the catalog's own keyPrefix for that provider", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      const key = `${entry.keyPrefix}test-key-000`;
      const result = validateBYOKKey(key, entry.id as BYOKProvider);
      expect(result).toBeNull();
    }
  });

  it("byokModelPresets(provider) matches the catalog's fallbackModels exactly", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(byokModelPresets(entry.id as BYOKProvider)).toEqual(entry.fallbackModels);
    }
  });
});
