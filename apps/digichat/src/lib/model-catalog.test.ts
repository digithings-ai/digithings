import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { MODEL_CATALOG_BYOK_PROVIDER_MAP } from "./model-catalog.generated";
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
  reasoning: false,
  vision: false,
  attachment: false,
  open_weights: false,
  tier: null,
  ...over,
});

type CatalogJson = {
  _meta: { providers: string[] };
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

  it("sorts `all` by id ascending", () => {
    const b = bucketCatalogEntries([entry({ id: "z" }), entry({ id: "a" }), entry({ id: "m" })]);
    expect(b.all.map((e) => e.id)).toEqual(["a", "m", "z"]);
  });

  it("buckets by the precomputed tier without re-deriving it", () => {
    // A cheap open-weight model and a flagship model both come from the
    // generator. The buckets below must agree with `tier`, not with any local
    // price or open-weight rule -- re-deriving here is the drift this module
    // exists to remove.
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
    expect(catalogEntriesFor("gemini")).toEqual(catalogEntriesFor("gemini"));
    const entries = catalogEntriesFor("gemini");
    expect(entries.length).toBeGreaterThan(0);
    expect(entries.map((e) => e.id)).toContain("gemini-2.5-flash");
  });

  it("returns an empty list for a provider the catalog does not carry", () => {
    // Never a throw: an unmapped provider must degrade to "no suggestions", not
    // break the picker.
    expect(catalogEntriesFor("nope" as BYOKProvider)).toEqual([]);
  });

  it("ships no base URL or env var alongside the metadata", () => {
    const serialized = JSON.stringify(catalogEntriesFor("openai"));
    expect(serialized).not.toContain("api.openai.com");
    expect(serialized).not.toContain("OPENAI_API_KEY");
    expect(serialized).not.toContain("npm");
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