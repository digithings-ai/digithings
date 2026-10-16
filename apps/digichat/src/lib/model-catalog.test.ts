import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  MODEL_CATALOG_BYOK_PROVIDER_MAP,
  MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS,
} from "./model-catalog.generated";
import {
  bucketCatalogEntries,
  catalogEntriesFor,
  type ModelCatalogEntry,
} from "./model-catalog";
import { BYOK_PROVIDER_LIST, type BYOKProvider } from "@/lib/byok-providers";

const entry = (over: Partial<ModelCatalogEntry> = {}): ModelCatalogEntry => ({
  id: "m",
  label: "M",
  cost_input_usd_per_million: null,
  cost_output_usd_per_million: null,
  context_window: null,
  max_output_tokens: null,
  modalities_input: [],
  modalities_output: [],
  tool_call: false,
  structured_output: null,
  reasoning: null,
  vision: false,
  attachment: null,
  open_weights: false,
  tier: null,
  ...over,
});

type CatalogJson = {
  _meta: { providers: string[] };
  models: Record<string, { id: string }[]>;
};

function loadCatalogJson(): CatalogJson {
  const path = resolve(process.cwd(), "../../config/model-catalog.json");
  return JSON.parse(readFileSync(path, "utf-8")) as CatalogJson;
}

describe("bucketCatalogEntries", () => {
  it("places an entry with no price in `all` only", () => {
    const b = bucketCatalogEntries([entry({ id: "unpriced" })]);
    expect(b.all.map((e) => e.id)).toEqual(["unpriced"]);
    expect(b.free).toEqual([]);
    expect(b.flagship).toEqual([]);
    expect(b.opensource).toEqual([]);
  });

  it("inherits the generator's order rather than re-sorting it", () => {
    // The generator already sorted each provider's rows by id. Re-sorting with
    // `localeCompare` here would make the picker's order depend on the server's
    // locale (2 of the 10 providers reorder under `en-CA`), which contradicts
    // what config/model-catalog.json and docs/MODEL_CATALOG.md promise.
    const outOfOrder = [entry({ id: "z" }), entry({ id: "a" }), entry({ id: "m" })];
    expect(bucketCatalogEntries(outOfOrder).all.map((e) => e.id)).toEqual(["z", "a", "m"]);
    // ...and the committed catalog really is byte-sorted per provider, so the
    // inherited order is the sorted one in practice.
    const catalog = loadCatalogJson();
    for (const rows of Object.values(catalog.models)) {
      expect(rows.map((r) => r.id)).toEqual([...rows.map((r) => r.id)].sort());
    }
  });

  it("buckets by the precomputed tier without re-deriving it", () => {
    // A cheap open-weight model and a flagship model both come from the
    // generator. The buckets below must agree with `tier`, not with any local
    // price or open-weight rule -- re-deriving here is the drift this module
    // exists to remove. Entries are supplied pre-sorted.
    const b = bucketCatalogEntries([
      entry({ id: "a", tier: "opensource" }),
      entry({ id: "b", tier: "flagship" }),
      entry({ id: "c", tier: "free" }),
      entry({ id: "d", tier: null }),
    ]);
    expect(b.free.map((e) => e.id)).toEqual(["c"]);
    expect(b.flagship.map((e) => e.id)).toEqual(["b"]);
    expect(b.opensource.map((e) => e.id)).toEqual(["a"]);
    expect(b.all.map((e) => e.id)).toEqual(["a", "b", "c", "d"]);
  });

  it("passes a stated tool-call claim through, and omits an absent one", () => {
    const b = bucketCatalogEntries([
      entry({ id: "with-tools", tool_call: true, tier: "opensource" }),
      entry({ id: "no-tools", tool_call: false, tier: "opensource" }),
      entry({ id: "unknown-tools", tool_call: null, tier: "opensource" }),
    ]);
    const byId = new Map(b.all.map((e) => [e.id, e]));
    expect(byId.get("with-tools")?.supportsTools).toBe(true);
    // A stated `false` survives -- models.dev said "no tool calls", which is a
    // claim. An absent claim is omitted, never defaulted to false.
    expect(byId.get("no-tools")?.supportsTools).toBe(false);
    expect(byId.get("unknown-tools")).not.toHaveProperty("supportsTools");
  });
});

describe("catalogEntriesFor", () => {
  it("maps gemini to the google catalog provider", () => {
    const entries = catalogEntriesFor("gemini");
    expect(entries.length).toBeGreaterThan(0);
    // Assert a *routable* id, not merely one models.dev carries: the catalog
    // still lists gemini-2.5-flash, but `config/litellm.yaml` has no
    // `model_name` for it, so the routable intersection (#5000) excludes it.
    // Asserting the unfiltered row here would pass on a member of the catalog
    // the picker can never route -- the defect F2 of PR #4997 was about.
    expect(entries.map((e) => e.id)).toContain("gemini-3.5-flash");
  });

  it("returns an empty list for a provider the catalog does not carry", () => {
    // Never a throw: an unmapped provider must degrade to "no suggestions", not
    // break the picker.
    expect(catalogEntriesFor("nope" as BYOKProvider)).toEqual([]);
  });

  it("offers only ids the house has a LiteLLM route for", () => {
    // The load-bearing filter. models.dev is a curated metadata database, not a
    // routing registry: offering a catalog id with no declared `model_name` is
    // a 500 on every BYOK chat that picks it, because config/litellm.yaml
    // routes strictly with no `fallbacks`.
    for (const id of BYOK_PROVIDER_LIST) {
      const routable = new Set(MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS[id] ?? []);
      for (const e of catalogEntriesFor(id)) {
        expect(routable, `${id}: ${e.id} is offered but has no LiteLLM model group`)
          .toContain(e.id);
      }
    }
    // And the filter is not vacuous: google carries 39 catalog rows and only a
    // handful are routed, so without the intersection almost everything would
    // be offered.
    expect(catalogEntriesFor("gemini").length).toBeLessThan(
      loadCatalogJson().models.google.length,
    );
  });

  it("covers every advertised BYOK preset, so no advertised option is lost", () => {
    // The other side of the same filter: intersecting must not silently drop an
    // id config/byok-providers.json advertises. Every advertised preset has to
    // survive the routable intersection, or the picker's first choice stops
    // working for that provider.
    const presets: Record<string, string[]> = {
      openai: ["gpt-4o-mini", "gpt-4o", "o4-mini"],
      xai: ["grok-4.3", "grok-4.5"],
      anthropic: ["claude-haiku-4-5", "claude-opus-4-5", "claude-sonnet-4-6"],
      gemini: ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.7-flash"],
    };
    for (const [provider, ids] of Object.entries(presets)) {
      // `offered` is by construction a subset of `routable` (catalogEntriesFor
      // filters by the routable set), so `routable.has(id)` is the whole claim:
      // every advertised preset is still routable, which is what keeps the
      // picker's first-choice option working. Spelled as a plain membership
      // check rather than the old `offered || routable` disjunction, which had
      // collapsed to `routable` and read like it was checking two things.
      const routable = new Set(MODEL_CATALOG_ROUTABLE_BYOK_MODEL_IDS[provider] ?? []);
      for (const id of ids) {
        expect(
          routable.has(id),
          `${provider}: advertised preset ${id} is not in the routable set`,
        ).toBe(true);
      }
    }
  });

  it("ships no base URL or env var alongside the metadata", () => {
    const serialized = JSON.stringify(catalogEntriesFor("openai"));
    expect(serialized).not.toContain("api.openai.com");
    expect(serialized).not.toContain("OPENAI_API_KEY");
    // Field-name assertions, not substring-on-arbitrary-text: `npm` as a
    // substring can only pass by accident, so it checks nothing. Anchored to the
    // whole key so `max_output_tokens` (which contains "token") is not a
    // false positive. The catalog's own schema pins the key set
    // (tests/config/test_model_catalog.py), so this is the belt to that braces.
    for (const e of catalogEntriesFor("openai")) {
      for (const key of Object.keys(e)) {
        expect(key).not.toMatch(/^(npm|env|api|url|key|token|secret|.*_url|.*_key)$/i);
      }
    }
  });
});

describe("BYOK_PROVIDER_TO_CATALOG_PROVIDER", () => {
  it("maps every BYOK provider to a provider present in the catalog", () => {
    const catalog = loadCatalogJson();
    for (const id of BYOK_PROVIDER_LIST) {
      const key = MODEL_CATALOG_BYOK_PROVIDER_MAP[id];
      expect(key, `no catalog provider for ${id}`).toBeTruthy();
      expect(catalog._meta.providers).toContain(key);
    }
  });

  it("agrees with the generated map on every rename", () => {
    expect(MODEL_CATALOG_BYOK_PROVIDER_MAP).toMatchObject({
      gemini: "google",
      together: "togetherai",
      fireworks: "fireworks-ai",
      openai: "openai",
      anthropic: "anthropic",
      xai: "xai",
      groq: "groq",
      openrouter: "openrouter",
      deepseek: "deepseek",
    });
  });
});