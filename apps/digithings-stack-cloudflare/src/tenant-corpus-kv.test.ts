import { afterEach, describe, expect, it, vi } from "vitest";

import { composeCorpusMap } from "./tenant-config";
import {
  TENANT_CORPUS_MAP_KEY,
  TENANT_CORPUS_MAP_MAX_BYTES,
  composeCorpusMapWithKv,
  readTenantCorpusMapKv,
} from "./tenant-corpus-kv";

const HOUSE = JSON.stringify({
  digithings: { digisearchIndex: "digithings_docs", vaultPathPrefix: "digithings/" },
});
const LEGACY = JSON.stringify({
  "tenant-a": { digisearchIndex: "tenant_a", lockSessionControls: true },
});
const PINNED = {
  webSearchDomains: ["example.com", "social.example/company/b", "posts.example/b_*"],
  webSearchMaxHosts: 11,
  webSearchPageCorpus: true,
  researchSystemPrompt: "Answer from the allowed sites only.",
  lockSessionControls: true,
};

afterEach(() => vi.restoreAllMocks());

describe("composeCorpusMapWithKv", () => {
  it("is byte-identical to the env-only map when the key is absent or blank", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    for (const raw of [null, undefined, "", "   "]) {
      expect(composeCorpusMapWithKv(HOUSE, LEGACY, raw)).toBe(composeCorpusMap(HOUSE, LEGACY));
      expect(composeCorpusMapWithKv(HOUSE, undefined, raw)).toBe(composeCorpusMap(HOUSE, undefined));
      expect(composeCorpusMapWithKv(undefined, undefined, raw)).toBe(composeCorpusMap(undefined, undefined));
    }
    expect(warn).not.toHaveBeenCalled();
  });

  it("adds a KV client entry with every field unchanged", () => {
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, LEGACY, JSON.stringify({ "tenant-b": PINNED })));
    expect(out["tenant-b"]).toEqual(PINNED);
    expect(out["tenant-a"]).toEqual(JSON.parse(LEGACY)["tenant-a"]);
    expect(out.digithings).toEqual(JSON.parse(HOUSE).digithings);
  });

  it("works with no private secret at all", () => {
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, undefined, JSON.stringify({ "tenant-b": PINNED })));
    expect(Object.keys(out)).toContain("tenant-b");
    expect(out["tenant-b"]).toEqual(PINNED);
  });

  it("falls back to the env map with a warning for malformed or unusable values", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    for (const raw of ["{", "[]", "42", '"text"', "null", JSON.stringify({ "tenant-b": "x" }), "{}"]) {
      warn.mockClear();
      expect(composeCorpusMapWithKv(HOUSE, LEGACY, raw)).toBe(composeCorpusMap(HOUSE, LEGACY));
      expect(warn).toHaveBeenCalledTimes(1);
      expect(String(warn.mock.calls[0][0])).toContain(TENANT_CORPUS_MAP_KEY);
    }
  });

  it("refuses an oversized value", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const big = JSON.stringify({ "tenant-b": { researchSystemPrompt: "x".repeat(TENANT_CORPUS_MAP_MAX_BYTES) } });
    expect(composeCorpusMapWithKv(HOUSE, LEGACY, big)).toBe(composeCorpusMap(HOUSE, LEGACY));
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("lets a KV entry replace the private entry for the same slug", () => {
    const replaced = { digisearchIndex: "tenant_a_v2" };
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, LEGACY, JSON.stringify({ "tenant-a": replaced })));
    expect(out["tenant-a"]).toEqual(replaced);
  });

  it("never lets a KV entry shadow the house entry or its alias", () => {
    const evil = { webSearchDomains: ["elsewhere.example"] };
    const raw = JSON.stringify({ digithings: evil, "digithings-ai": evil, "tenant-b": PINNED });
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, LEGACY, raw));
    const house = JSON.parse(HOUSE).digithings;
    expect(out.digithings).toEqual(house);
    expect(out["digithings-ai"]).toEqual(house);
    expect(out["tenant-b"]).toEqual(PINNED);
  });

  it("still applies KV entries when the private secret is unusable", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, "{", JSON.stringify({ "tenant-b": PINNED })));
    expect(out["tenant-b"]).toEqual(PINNED);
    expect(out["tenant-a"]).toBeUndefined();
    expect(warn).toHaveBeenCalled();
  });
});

describe("readTenantCorpusMapKv", () => {
  it("reads the one key, and treats a missing binding or KV error as no value", async () => {
    const seen: string[] = [];
    const ok = { get: async (k: string) => (seen.push(k), "{}") };
    expect(await readTenantCorpusMapKv(ok)).toBe("{}");
    expect(seen).toEqual([TENANT_CORPUS_MAP_KEY]);
    expect(await readTenantCorpusMapKv(undefined)).toBeNull();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const boom = { get: async () => { throw new Error("kv down"); } };
    expect(await readTenantCorpusMapKv(boom)).toBeNull();
    expect(warn).toHaveBeenCalledTimes(1);
  });
});
