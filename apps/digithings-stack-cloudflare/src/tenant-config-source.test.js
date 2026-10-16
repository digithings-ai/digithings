import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  DIGITHINGS_ONLY_CORPUS_JSON,
  DIGITHINGS_ONLY_CORPUS_MAP,
  parseCorpusMapJson,
  projectEmbedTenantsToCorpusMap,
} from "./tenant-config";

/**
 * Ties `DIGITHINGS_ONLY_CORPUS_MAP` to the literal it replaces.
 *
 * `tenant-config.ts` duplicates one tenant's corpus routing as a constant, and
 * `index.ts` still carries the same routing inside the
 * `DIGI_TENANT_CORPUS_MAP` fallback literal this leaf is preparing to retire.
 * Two hand-kept copies of the same values is the drift this repo already has two
 * Python guards for (`tests/scripts/test_check_tenant_corpus_map.py` and
 * `tests/dg/test_tenant_corpus_parity.py`), so the copy shipping with this leaf
 * gets its own parity check instead of being assumed correct.
 *
 * The literal is read as SOURCE TEXT -- `index.ts` is a Workers entrypoint whose
 * Container runtime is not constructible in a test, so importing it is not an
 * option. Two consequences, both handled explicitly below:
 *
 *  - The extraction regex mirrors `_FALLBACK_RE` in
 *    `scripts/check_tenant_corpus_map.py`. If the scrub that retires this
 *    literal changes its source shape, the capture goes empty and this file
 *    FAILS on the empty capture rather than passing on an empty comparison.
 *  - The capture is JS source text, not the runtime string. Its OCC prompt
 *    contains `\\n`, `\\"` and `\\u2014`, which the Workers runtime collapses to
 *    one backslash each. `unescapeSingleQuoted` reproduces exactly that collapse
 *    and refuses any backslash run it did not measure, so a future edit that
 *    introduces `\\\\` or a `\x` escape fails loudly instead of being silently
 *    mis-unescaped into a parse that happens to succeed.
 *
 * Deliberately plain `.js` for the reason documented in `env-vars-pin.test.js`:
 * `tsconfig.json` scopes `types` to `@cloudflare/workers-types`, so `node:fs` has
 * no ambient declaration here, and `tsconfig.json`'s `include` only matches
 * TypeScript sources -- this file is invisible to `tsc --noEmit`, and vitest
 * still collects it through the `.test.{ts,js}` glob.
 */

const SRC_DIR = dirname(fileURLToPath(import.meta.url));
const INDEX_TS = join(SRC_DIR, "index.ts");

/** Mirrors `_FALLBACK_RE` in `scripts/check_tenant_corpus_map.py`. */
const FALLBACK_RE =
  /DIGI_TENANT_CORPUS_MAP:\s*env\.DIGI_TENANT_CORPUS_MAP\s*\?\?\s*'((?:[^'\\]|\\.)*)'/;

/** The only corpus keys the drift gate compares; siblings are out of scope. */
const FIELDS = ["digisearchIndex", "vaultPathPrefix"];

function indexSource() {
  return readFileSync(INDEX_TS, "utf8");
}

/** Source text of the legacy literal's single-quoted body, or `null`. */
function legacyLiteralSource() {
  const match = FALLBACK_RE.exec(indexSource());
  return match ? match[1] : null;
}

/**
 * Collapse the JS single-quoted escapes the capture contains, so the result is
 * the string the Workers runtime would build. Every run must be exactly two
 * backslashes (`\\` -> `\`); anything else is refused rather than guessed at.
 */
function unescapeSingleQuoted(source) {
  for (const run of source.match(/\\+/g) ?? []) {
    if (run.length !== 2) {
      throw new Error(
        `legacy literal holds a ${run.length}-backslash run; the runtime unescape ` +
          "for it is not implemented here, so re-derive it before trusting this file",
      );
    }
  }
  return source.replace(/\\\\/g, "\\");
}

/** The legacy corpus map literal in `index.ts`, or `null` if unlocatable. */
function legacyLiteral() {
  const source = legacyLiteralSource();
  return source === null ? null : JSON.parse(unescapeSingleQuoted(source));
}

function corpusFields(entry) {
  const out = {};
  for (const field of FIELDS) out[field] = entry[field];
  return out;
}

/** The literal's `digithings` entry, shaped the way KV would deliver it. */
function digithingsEmbedEntry() {
  return {
    "digithings.ai": {
      slug: "digithings",
      token: "unused-by-this-test",
      backend: {
        digisearchIndex: "digithings_docs",
        vaultPathPrefix: "clients/digithings",
        type: "digisearch",
      },
    },
  };
}

describe("tenant-config: the digithings-only constant matches what it replaces", () => {
  it("locates and unescapes the legacy literal in index.ts (non-vacuity)", () => {
    // Without this the parity assertions below could pass on two empty objects.
    const source = legacyLiteralSource();
    expect(source).not.toBeNull();
    expect(source.length).toBeGreaterThan(500);

    const literal = legacyLiteral();
    expect(typeof literal).toBe("object");
    expect(Object.keys(literal)).toContain("digithings");
    // A known-present sibling tenant, so this check is not satisfied by a
    // single entry the scrub could have deleted alongside ours.
    expect(Object.keys(literal)).toContain("occ");
    // The escape handling is load-bearing: without it the parse throws above.
    expect(source).toContain("\\\\n");
  });

  it("carries exactly the first-party tenant", () => {
    // A client tenant inside the first-party-only constant would keep that
    // tenant alive after the literal is retired -- the fail-open direction.
    expect(Object.keys(DIGITHINGS_ONLY_CORPUS_MAP)).toEqual(["digithings"]);
  });

  it("agrees with the digithings entry of the index.ts literal", () => {
    const fromLiteral = corpusFields(legacyLiteral().digithings);
    expect(DIGITHINGS_ONLY_CORPUS_MAP.digithings).toEqual(fromLiteral);
  });

  it("agrees with the KV projection of the same tenant", () => {
    const projected = projectEmbedTenantsToCorpusMap(digithingsEmbedEntry());
    expect(projected).toEqual(DIGITHINGS_ONLY_CORPUS_MAP);
  });

  it("round-trips through the legacy parser as the same map", () => {
    expect(parseCorpusMapJson(DIGITHINGS_ONLY_CORPUS_JSON)).toEqual(
      DIGITHINGS_ONLY_CORPUS_MAP,
    );
  });

  it("keeps the constant free of a client tenant a KV document names", () => {
    // Arms are REPLACED, not merged: a KV document naming `occ` answers on its
    // own and is never unioned with the first-party constant, and the constant
    // itself carries no client tenant. Asserted as a pair because either half
    // alone is satisfied by a projection that simply ignored `occ`.
    const projected = projectEmbedTenantsToCorpusMap({
      "occ.digithings.ai": {
        slug: "occ",
        token: "unused-by-this-test",
        backend: { digisearchIndex: "occ_help", vaultPathPrefix: "clients/occ" },
      },
    });
    expect(Object.keys(projected)).toEqual(["occ"]);
    expect(DIGITHINGS_ONLY_CORPUS_MAP).not.toHaveProperty("occ");
  });
});
