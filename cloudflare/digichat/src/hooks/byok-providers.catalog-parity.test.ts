import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  BYOK_PROVIDER_LIST,
  byokKeyPrefixError,
  byokRequiresModel,
  isByokProvider,
  readByokProvider,
  type BYOKProvider,
} from "@/lib/byok-providers";

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

/**
 * `use-byok-key.catalog-parity.test.ts` proves the client hook's hand-copies
 * stay in parity with `config/byok-providers.json`. This file proves the
 * SAME thing against `@/lib/byok-providers` directly — the module
 * `api/chat/route.ts` and `api/byok/test/route.ts` now import their
 * provider-list / requiresModel / prefix-validation logic from (#2351).
 *
 * Before #2351, there were three independent hand-copies of the provider
 * list/prefix rules (the hook, `chat/route.ts`'s `byokNeedsModel` OR-chain,
 * `byok/test/route.ts`'s `readProvider` + 5 prefix `if`s). Now there is one
 * (`BYOK_PROVIDER_CATALOG` inside `byok-providers.ts`), and both route
 * handlers call into it via `byokRequiresModel` / `readByokProvider` /
 * `byokKeyPrefixError`. Because every assertion below iterates the catalog
 * loaded fresh from JSON, a provider added only to
 * `config/byok-providers.json` (and mirrored into `byok-providers.ts`'s own
 * catalog, but nowhere else) is exactly the case these tests catch drift on
 * — and since neither route handler hand-lists a provider name anymore,
 * that mirroring is the *only* change either route needs.
 */
describe("byok-providers <-> config/byok-providers.json parity (the server route handlers' source of truth)", () => {
  it("BYOK_PROVIDER_LIST (imported by both route handlers) contains exactly the catalog's provider ids", () => {
    const catalog = loadCatalog();
    const catalogIds = new Set(catalog.map((e) => e.id));
    const tsIds = new Set(BYOK_PROVIDER_LIST as readonly string[]);
    expect(tsIds).toEqual(catalogIds);
  });

  it("byokRequiresModel — the exact predicate chat/route.ts calls in place of its old byokNeedsModel OR-chain — agrees with the catalog's requiresModel per provider", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(byokRequiresModel(entry.id)).toBe(Boolean(entry.requiresModel));
    }
  });

  it("readByokProvider/isByokProvider — the exact parser byok/test/route.ts calls in place of its old readProvider — recognize every catalog provider id as known", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(readByokProvider(entry.id)).toBe(entry.id);
      expect(isByokProvider(entry.id)).toBe(true);
    }
  });

  it("byokKeyPrefixError — the exact check byok/test/route.ts calls in place of its old 5 hand-written prefix if-blocks — rejects a key that doesn't start with the catalog's keyPrefix", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      expect(KEY_NOT_MATCHING_ANY_PREFIX.startsWith(entry.keyPrefix)).toBe(false);
      const result = byokKeyPrefixError(KEY_NOT_MATCHING_ANY_PREFIX, entry.id as BYOKProvider);
      expect(result).not.toBeNull();
    }
  });

  it("byokKeyPrefixError accepts a key built from the catalog's own keyPrefix for that provider", () => {
    const catalog = loadCatalog();
    for (const entry of catalog) {
      const key = `${entry.keyPrefix}test-key-000`;
      const result = byokKeyPrefixError(key, entry.id as BYOKProvider);
      expect(result).toBeNull();
    }
  });

  // The deliberate behavior *improvement* in #2351 (acceptance criterion 3):
  // a provider name that names no catalog entry — simulating one added only
  // to a future config/byok-providers.json revision and not yet mirrored
  // into byok-providers.ts's own catalog — must never be silently coerced
  // into a known provider by either route handler's logic. The old
  // `readProvider` in byok/test/route.ts fell through to `"openai"` for
  // exactly this case; `readByokProvider` must not.
  it("a provider name absent from the catalog is never silently coerced to a known provider by the shared predicates both routes call", () => {
    const catalog = loadCatalog();
    const hypotheticalUnmirroredProvider = "mistral";
    expect(catalog.some((e) => e.id === hypotheticalUnmirroredProvider)).toBe(false);
    expect(BYOK_PROVIDER_LIST as readonly string[]).not.toContain(
      hypotheticalUnmirroredProvider,
    );

    // byok/test/route.ts's exact call path: comes back null, not "openai".
    expect(readByokProvider(hypotheticalUnmirroredProvider)).toBeNull();
    expect(isByokProvider(hypotheticalUnmirroredProvider)).toBe(false);

    // chat/route.ts's exact call path: a pure boolean gate, never throws on
    // an unrecognized value, and never claims a model is required for a
    // provider it doesn't know (same as the old OR-chain's implicit default).
    expect(byokRequiresModel(hypotheticalUnmirroredProvider)).toBe(false);
  });
});
