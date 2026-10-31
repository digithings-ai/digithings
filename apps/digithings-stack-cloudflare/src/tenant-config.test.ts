/**
 * Unit gate for the `TENANT_CONFIG` KV read path (DIG-3699).
 *
 * Discriminating tests, not contract mirrors: each one fails if the behaviour
 * it names is removed. The parity check that keeps the first-party constant in
 * step with `index.ts` lives in `tenant-config-source.test.js` (it reads a file
 * from disk, which this package's Workers-only tsconfig cannot type).
 */
import { describe, expect, it } from "vitest";

import {
  DIGITHINGS_ONLY_CORPUS_JSON,
  DIGITHINGS_ONLY_CORPUS_MAP,
  TENANT_CONFIG_KEY,
  TENANT_CONFIG_TTL_MS,
  cachedTenantConfig,
  parseCorpusMapJson,
  projectEmbedTenantsToCorpusMap,
  readTenantConfig,
  resetTenantConfigCache,
  type TenantConfigStore,
  withHouseSlugAlias,
} from "./tenant-config";

function store(value: string | null | Error, calls: string[] = []): TenantConfigStore {
  return {
    async get(key: string) {
      calls.push(key);
      if (value instanceof Error) throw value;
      return value;
    },
  };
}

const OCC_ENTRY = {
  token: "tkn",
  slug: "occ",
  gateMode: "help",
  backend: {
    type: "digisearch",
    digisearchIndex: "occ_help",
    vaultPathPrefix: "clients/online-compliance-center",
  },
};

const FIRST_PARTY_ENTRY = {
  token: "tkn2",
  slug: "digithings",
  backend: { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
};

const KV_DOCUMENT = JSON.stringify({
  "digithings.ai": FIRST_PARTY_ENTRY,
  "occ.digithings.ai": OCC_ENTRY,
});

describe("projectEmbedTenantsToCorpusMap", () => {
  it("rekeys the host-keyed embed document by slug and adds the house alias", () => {
    expect(projectEmbedTenantsToCorpusMap(JSON.parse(KV_DOCUMENT))).toEqual({
      digithings: { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
      "digithings-ai": {
        digisearchIndex: "digithings_docs",
        vaultPathPrefix: "clients/digithings",
      },
      occ: {
        digisearchIndex: "occ_help",
        vaultPathPrefix: "clients/online-compliance-center",
      },
    });
  });

  it("resolves the live house slug digithings-ai to the same corpus as digithings", () => {
    // The production KV document names the house tenant `digithings-ai`; the
    // map has historically been read as `digithings`. Both must answer, and
    // with the same index and prefix, or digivault refuses the live chat (403).
    const document = {
      "digithings.ai": {
        ...FIRST_PARTY_ENTRY,
        slug: "digithings-ai",
        backend: { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
      },
    };
    const projected = projectEmbedTenantsToCorpusMap(document);
    expect(projected.digithings).toEqual({
      digisearchIndex: "digithings_docs",
      vaultPathPrefix: "clients/digithings",
    });
    expect(projected["digithings-ai"]).toEqual(projected.digithings);
    expect(Object.keys(projected)).toEqual(["digithings", "digithings-ai"]);
  });

  it("does not invent a house entry for an unknown tenant", () => {
    const projected = projectEmbedTenantsToCorpusMap({
      "x.example": {
        slug: "x",
        backend: { digisearchIndex: "x_docs", vaultPathPrefix: "clients/x" },
      },
    });
    expect(Object.keys(projected)).toEqual(["x"]);
    expect(projected).not.toHaveProperty("digithings");
    expect(projected).not.toHaveProperty("digithings-ai");
  });

  it("drops a tenant with no backend", () => {
    const document = { "x.example": { slug: "x", token: "t", gateMode: "help" } };
    expect(projectEmbedTenantsToCorpusMap(document)).toEqual({});
  });

  it("drops a tenant whose backend carries no index", () => {
    const document = { "x.example": { slug: "x", backend: { vaultPathPrefix: "clients/x" } } };
    expect(projectEmbedTenantsToCorpusMap(document)).toEqual({});
  });

  it("drops a blank or non-string slug", () => {
    const backend = { digisearchIndex: "idx" };
    expect(
      projectEmbedTenantsToCorpusMap({
        a: { slug: "   ", backend },
        b: { slug: 7, backend },
        c: { backend },
      }),
    ).toEqual({});
  });

  it("ignores non-object entries and a non-object document", () => {
    expect(projectEmbedTenantsToCorpusMap({ a: "nope", b: null, c: ["x"] })).toEqual({});
    expect(projectEmbedTenantsToCorpusMap("not a document")).toEqual({});
    expect(projectEmbedTenantsToCorpusMap(null)).toEqual({});
    expect(projectEmbedTenantsToCorpusMap([FIRST_PARTY_ENTRY])).toEqual({});
  });

  it("carries a backend research prompt when the KV value supplies one", () => {
    const document = {
      "occ.digithings.ai": {
        ...OCC_ENTRY,
        backend: { ...OCC_ENTRY.backend, researchSystemPrompt: "You are OCC." },
      },
    };
    expect(projectEmbedTenantsToCorpusMap(document).occ).toEqual({
      digisearchIndex: "occ_help",
      vaultPathPrefix: "clients/online-compliance-center",
      researchSystemPrompt: "You are OCC.",
    });
  });

  it("blanks a non-string prefix instead of stringifying it", () => {
    const document = {
      "x.example": { slug: "x", backend: { digisearchIndex: "idx", vaultPathPrefix: 1234 } },
    };
    expect(projectEmbedTenantsToCorpusMap(document).x).toEqual({
      digisearchIndex: "idx",
      vaultPathPrefix: "",
    });
  });
});

describe("withHouseSlugAlias", () => {
  it("keeps the canonical digithings entry when both house keys are present", () => {
    const aliased = withHouseSlugAlias({
      digithings: { digisearchIndex: "canonical", vaultPathPrefix: "clients/digithings" },
      "digithings-ai": { digisearchIndex: "stale", vaultPathPrefix: "clients/stale" },
      occ: { digisearchIndex: "occ_help" },
    });
    expect(aliased.digithings).toEqual({
      digisearchIndex: "canonical",
      vaultPathPrefix: "clients/digithings",
    });
    expect(aliased["digithings-ai"]).toEqual(aliased.digithings);
    expect(aliased.occ).toEqual({ digisearchIndex: "occ_help" });
    expect(Object.keys(aliased)).toEqual(["digithings", "digithings-ai", "occ"]);
  });

  it("adds the canonical key for a map that only has the live slug", () => {
    const aliased = withHouseSlugAlias({
      "digithings-ai": { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
    });
    expect(Object.keys(aliased)).toEqual(["digithings", "digithings-ai"]);
    expect(aliased.digithings).toEqual(aliased["digithings-ai"]);
  });

  it("returns a map with no house slug unchanged and invents nothing", () => {
    const input = { occ: { digisearchIndex: "occ_help" } };
    expect(withHouseSlugAlias(input)).toBe(input);
  });

  it("does not let an empty canonical entry shadow a usable live entry", () => {
    const aliased = withHouseSlugAlias({
      digithings: {},
      "digithings-ai": { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
    });
    expect(aliased.digithings).toEqual({
      digisearchIndex: "digithings_docs",
      vaultPathPrefix: "clients/digithings",
    });
    expect(aliased["digithings-ai"]).toEqual(aliased.digithings);
  });

  it("leaves an unusable house entry alone when no usable one exists", () => {
    const input = { digithings: {} };
    expect(withHouseSlugAlias(input)).toBe(input);
  });
});

describe("parseCorpusMapJson", () => {
  it("rejects a non-object, an empty object and malformed JSON", () => {
    expect(parseCorpusMapJson("[]")).toBeUndefined();
    expect(parseCorpusMapJson("{}")).toBeUndefined();
    expect(parseCorpusMapJson("{oops")).toBeUndefined();
    expect(parseCorpusMapJson("")).toBeUndefined();
    expect(parseCorpusMapJson(undefined)).toBeUndefined();
  });

  it("keeps object-valued entries and drops scalar ones", () => {
    expect(parseCorpusMapJson('{"occ":{"digisearchIndex":"i"},"bad":7}')).toEqual({
      occ: { digisearchIndex: "i" },
    });
  });
});

describe("readTenantConfig", () => {
  it("prefers KV over the legacy vars string and reads the agreed key", async () => {
    const calls: string[] = [];
    const resolved = await readTenantConfig({
      store: store(KV_DOCUMENT, calls),
      legacyJson: JSON.stringify({ occ: { digisearchIndex: "stale" } }),
    });
    expect(calls).toEqual([TENANT_CONFIG_KEY]);
    expect(resolved.source).toBe("kv");
    expect(resolved.map.occ).toEqual({
      digisearchIndex: "occ_help",
      vaultPathPrefix: "clients/online-compliance-center",
    });
  });

  it("does not merge the legacy arm into a KV answer", async () => {
    const resolved = await readTenantConfig({
      store: store(JSON.stringify({ "x.example": { slug: "x", backend: { digisearchIndex: "i" } } })),
      legacyJson: JSON.stringify({ occ: { digisearchIndex: "occ_help" } }),
    });
    expect(resolved.map.occ).toBeUndefined();
  });

  it("falls through to legacy vars when KV is unbound", async () => {
    const resolved = await readTenantConfig({ legacyJson: JSON.stringify({ occ: { digisearchIndex: "occ_help" } }) });
    expect(resolved.source).toBe("legacy-vars");
    expect(resolved.map.occ).toEqual({ digisearchIndex: "occ_help" });
  });

  it("falls through to legacy vars when the KV read throws", async () => {
    const resolved = await readTenantConfig({
      store: store(new Error("kv unavailable")),
      legacyJson: JSON.stringify({ occ: { digisearchIndex: "occ_help" } }),
    });
    expect(resolved.source).toBe("legacy-vars");
  });

  it("falls through to legacy vars when the KV value is missing or empty", async () => {
    const legacyJson = JSON.stringify({ occ: { digisearchIndex: "occ_help" } });
    expect((await readTenantConfig({ store: store(null), legacyJson })).source).toBe("legacy-vars");
    expect((await readTenantConfig({ store: store("{}"), legacyJson })).source).toBe("legacy-vars");
    expect((await readTenantConfig({ store: store("{oops"), legacyJson })).source).toBe("legacy-vars");
  });

  it("lands on the first-party-only constant with nothing else configured", async () => {
    const resolved = await readTenantConfig({});
    expect(resolved.source).toBe("fallback");
    expect(resolved.map).toEqual(DIGITHINGS_ONLY_CORPUS_MAP);
    expect(resolved.json).toBe(DIGITHINGS_ONLY_CORPUS_JSON);
    expect(Object.keys(resolved.map)).toEqual(["digithings", "digithings-ai"]);
    expect(resolved.map["digithings-ai"]).toEqual(resolved.map.digithings);
  });

  it("adds the house alias to the legacy [vars] arm", async () => {
    const resolved = await readTenantConfig({
      legacyJson: JSON.stringify({
        digithings: { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
      }),
    });
    expect(resolved.source).toBe("legacy-vars");
    expect(resolved.map["digithings-ai"]).toEqual(resolved.map.digithings);
  });

  it("keeps the canonical house key for a KV document keyed by the live slug", async () => {
    const document = JSON.stringify({
      "digithings.ai": {
        slug: "digithings-ai",
        backend: { digisearchIndex: "digithings_docs", vaultPathPrefix: "clients/digithings" },
      },
    });
    const resolved = await readTenantConfig({ store: store(document) });
    expect(resolved.source).toBe("kv");
    expect(resolved.map.digithings).toEqual({
      digisearchIndex: "digithings_docs",
      vaultPathPrefix: "clients/digithings",
    });
    expect(resolved.map["digithings-ai"]).toEqual(resolved.map.digithings);
  });

  it("never throws, whatever the store does", async () => {
    const hostile: TenantConfigStore = {
      async get() {
        throw new Error("boom");
      },
    };
    await expect(readTenantConfig({ store: hostile })).resolves.toMatchObject({ source: "fallback" });
  });

  it("serialises an answer a consumer can JSON.parse", async () => {
    const resolved = await readTenantConfig({ store: store(KV_DOCUMENT) });
    expect(JSON.parse(resolved.json)).toEqual(resolved.map);
  });
});

describe("cachedTenantConfig", () => {
  it("reads the store once per TTL and again after it", async () => {
    resetTenantConfigCache();
    const calls: string[] = [];
    const env = { store: store(KV_DOCUMENT, calls) };

    expect((await cachedTenantConfig(env, 1_000)).source).toBe("kv");
    expect((await cachedTenantConfig(env, 1_000 + TENANT_CONFIG_TTL_MS - 1)).source).toBe("kv");
    expect(calls).toHaveLength(1);

    expect((await cachedTenantConfig(env, 1_000 + TENANT_CONFIG_TTL_MS)).source).toBe("kv");
    expect(calls).toHaveLength(2);
    resetTenantConfigCache();
  });

  it("does not answer from cache after a reset", async () => {
    resetTenantConfigCache();
    const calls: string[] = [];
    const env = { store: store(KV_DOCUMENT, calls) };
    await cachedTenantConfig(env, 5_000);
    resetTenantConfigCache();
    await cachedTenantConfig(env, 5_000);
    expect(calls).toHaveLength(2);
  });
});
