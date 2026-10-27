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
 * Ties `DIGITHINGS_ONLY_CORPUS_MAP` to the wiring that uses it.
 *
 * Until 2026-10-25 `index.ts` carried a full copy of the corpus map as the
 * `DIGI_TENANT_CORPUS_MAP` `??` fallback, and this file pinned the constant
 * against that literal so two hand-kept copies could not drift. That literal is
 * gone: the map is now two wrangler `[vars]` composed by `composeCorpusMap`
 * (Cloudflare refused the single 5285-byte binding with error 10054), and the
 * constant is the floor that function returns when neither half is usable.
 *
 * So the drift this file guards is no longer "do the two copies agree" but "is
 * there still only ONE copy". A tenant map re-appearing in `index.ts` would put
 * the deployment back over the binding cap and re-fork the answers, so it is
 * refused here rather than discovered at deploy time.
 *
 * `index.ts` is read as SOURCE TEXT -- it is a Workers entrypoint whose
 * Container runtime is not constructible in a test, so importing it is not an
 * option. Deliberately plain `.js` for the reason documented in
 * `env-vars-pin.test.js`: `tsconfig.json` scopes `types` to
 * `@cloudflare/workers-types`, so `node:fs` has no ambient declaration here.
 */

const SRC_DIR = dirname(fileURLToPath(import.meta.url));
const INDEX_TS = join(SRC_DIR, "index.ts");

function indexSource() {
  return readFileSync(INDEX_TS, "utf8");
}

/**
 * The container's `DIGI_TENANT_CORPUS_MAP` entry from `envVars`, or `null`.
 *
 * Scoped from the key to the next 4-space-indented key so a neighbouring
 * entry's `env.*` reference can never satisfy the assertions below.
 */
function corpusMapEntry() {
  const match = /^ {4}DIGI_TENANT_CORPUS_MAP:([\s\S]{0,400}?)\n {4}[A-Z]/m.exec(indexSource());
  return match ? match[1] : null;
}

/** The literal `digithings` entry, shaped the way KV would deliver it. */
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

describe("tenant-config: the digithings-only constant is the only copy left", () => {
  it("composes the split [vars] pair in index.ts (non-vacuity)", () => {
    // Without this the assertions below could pass on a source that simply says
    // nothing about the corpus map at all.
    const entry = corpusMapEntry();
    expect(entry).not.toBeNull();
    expect(entry).toContain("composeCorpusMap(");
    expect(entry).toContain("env.DIGI_TENANT_CORPUS_MAP");
    expect(entry).toContain("env.DIGI_TENANT_CORPUS_MAP_EXTRA");
  });

  it("carries no tenant corpus map in index.ts", () => {
    // The 5.1 kB regression, stated as a property of the source: whichever way
    // a literal crept back in, it would have to carry a prompt to do any harm,
    // and the Worker source must not contain one.
    expect(indexSource()).not.toContain("researchSystemPrompt");
    expect(indexSource()).not.toContain("digisearchIndex");
  });

  it("carries exactly the first-party tenant, under both house slugs", () => {
    // A client tenant inside the first-party-only constant would keep that
    // tenant alive after the literal is retired -- the fail-open direction. The
    // two house keys are one tenant, and both are needed: the live embed slug is
    // `digithings-ai`, while old callers read `digithings` (DIG-5638).
    expect(Object.keys(DIGITHINGS_ONLY_CORPUS_MAP)).toEqual(["digithings", "digithings-ai"]);
    expect(DIGITHINGS_ONLY_CORPUS_MAP["digithings-ai"]).toEqual(
      DIGITHINGS_ONLY_CORPUS_MAP.digithings,
    );
  });

  it("agrees with the routed fields the retired literal carried", () => {
    // The constant deliberately omits the house prompt: `composeCorpusMap`
    // serialises the [vars] halves for the deployed prompt, and this floor only
    // has to answer with a reachable first-party corpus.
    expect(DIGITHINGS_ONLY_CORPUS_MAP.digithings).toEqual({
      digisearchIndex: "digithings_docs",
      vaultPathPrefix: "clients/digithings",
    });
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
