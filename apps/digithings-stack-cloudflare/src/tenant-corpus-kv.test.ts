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

describe("composeCorpusMapWithKv: slugs are judged as the consumers read them", () => {
  const EVIL = { digisearchIndex: "stolen", vaultPathPrefix: "clients/other/", webSearchDomains: ["x.example"] };
  const house = JSON.parse(HOUSE).digithings;

  it("drops case and whitespace variants of the house slugs with a warning", () => {
    for (const slug of ["DIGITHINGS", " digithings", "Digithings-AI", "\tdigithings-ai", "digithings\n", "DigiThings-Ai "]) {
      const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
      const out = JSON.parse(
        composeCorpusMapWithKv(HOUSE, LEGACY, JSON.stringify({ [slug]: EVIL, "tenant-b": PINNED })),
      );
      expect(Object.keys(out)).toEqual(["digithings", "digithings-ai", "tenant-a", "tenant-b"]);
      expect(out.digithings).toEqual(house);
      expect(out["digithings-ai"]).toEqual(house);
      expect(out["tenant-b"]).toEqual(PINNED);
      expect(warn.mock.calls.some((c) => String(c[0]).includes("house tenant"))).toBe(true);
      warn.mockRestore();
    }
  });

  it("falls back to the env map when every KV slug is a house look-alike", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const raw = JSON.stringify({ DIGITHINGS: EVIL, " digithings-ai": EVIL });
    expect(composeCorpusMapWithKv(HOUSE, LEGACY, raw)).toBe(composeCorpusMap(HOUSE, LEGACY));
    expect(warn).toHaveBeenCalled();
  });

  it("drops every KV slug in a group that collides once normalised", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const raw = JSON.stringify({ "Tenant-C": { digisearchIndex: "c1" }, " tenant-c": { digisearchIndex: "c2" }, "tenant-b": PINNED });
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, LEGACY, raw));
    expect(Object.keys(out)).toEqual(["digithings", "digithings-ai", "tenant-a", "tenant-b"]);
    expect(warn.mock.calls.some((c) => String(c[0]).includes("collide"))).toBe(true);
  });

  it("drops a blank KV slug", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, LEGACY, JSON.stringify({ "  ": EVIL, "tenant-b": PINNED })));
    expect(Object.keys(out)).toEqual(["digithings", "digithings-ai", "tenant-a", "tenant-b"]);
    expect(warn).toHaveBeenCalled();
  });

  it("stores a non-canonical KV slug under its normalised form, replacing the private entry", () => {
    const vi2 = { digisearchIndex: "tenant_a_v2" };
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, LEGACY, JSON.stringify({ " Tenant-A ": vi2 })));
    expect(out["tenant-a"]).toEqual(vi2);
    expect(Object.keys(out)).toEqual(["digithings", "digithings-ai", "tenant-a"]);
  });

  it("hardens the private-secret path the same way", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const priv = JSON.stringify({ DIGITHINGS: EVIL, "\tdigithings-ai": EVIL, "tenant-a": { digisearchIndex: "a" } });
    for (const kv of [null, JSON.stringify({ "tenant-b": PINNED })]) {
      const out = JSON.parse(composeCorpusMapWithKv(HOUSE, priv, kv));
      expect(out.digithings).toEqual(house);
      expect(out["digithings-ai"]).toEqual(house);
      expect(out["tenant-a"]).toEqual({ digisearchIndex: "a" });
      expect(Object.keys(out).filter((k) => k.trim().toLowerCase().startsWith("digithings"))).toEqual([
        "digithings",
        "digithings-ai",
      ]);
    }
    expect(warn).toHaveBeenCalled();
  });

  it("never emits two keys a consumer would read as the same tenant", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const priv = JSON.stringify({ "tenant-a": { digisearchIndex: "a" }, "TENANT-A": { digisearchIndex: "A" } });
    const kv = JSON.stringify({ "Tenant-B": PINNED, "tenant-c ": { digisearchIndex: "c" } });
    const keys = Object.keys(JSON.parse(composeCorpusMapWithKv(HOUSE, priv, kv)));
    const norm = keys.map((k) => k.trim().toLowerCase());
    expect(new Set(norm).size).toBe(keys.length);
    expect(keys).toEqual(norm);
  });
});

describe("composeCorpusMapWithKv: only slugs digigraph accepts ship", () => {
  const EVIL = { digisearchIndex: "stolen", vaultPathPrefix: "clients/other/", webSearchDomains: ["x.example"] };
  const house = JSON.parse(HOUSE).digithings;
  // Python str.strip() removes these but JS trim() does not, so without the
  // slug rule they reach a consumer as the house tenant.
  const SNEAKY = [
    "\u001cdigithings",
    "digithings\u001f",
    "\u0085digithings-ai",
    "\u001ddigithings-ai\u001e",
    "DIGITHIN\u212aS-ai",
  ];

  it("drops control-character and non-ASCII house look-alikes from KV, with a warning", () => {
    for (const slug of SNEAKY) {
      const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
      const out = JSON.parse(
        composeCorpusMapWithKv(HOUSE, LEGACY, JSON.stringify({ [slug]: EVIL, "tenant-b": PINNED })),
      );
      expect(Object.keys(out)).toEqual(["digithings", "digithings-ai", "tenant-a", "tenant-b"]);
      expect(out.digithings).toEqual(house);
      expect(out["digithings-ai"]).toEqual(house);
      expect(warn).toHaveBeenCalled();
      warn.mockRestore();
    }
  });

  it("drops the same look-alikes from the private secret, with a warning", () => {
    for (const slug of SNEAKY) {
      const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
      const priv = JSON.stringify({ [slug]: EVIL, "tenant-a": { digisearchIndex: "a" } });
      for (const kv of [null, JSON.stringify({ "tenant-b": PINNED })]) {
        const out = JSON.parse(composeCorpusMapWithKv(HOUSE, priv, kv));
        expect(out.digithings).toEqual(house);
        expect(out["digithings-ai"]).toEqual(house);
        expect(out["tenant-a"]).toEqual({ digisearchIndex: "a" });
        expect(Object.keys(out).every((k) => /^[a-z0-9][a-z0-9-]*$/.test(k))).toBe(true);
      }
      expect(warn).toHaveBeenCalled();
      warn.mockRestore();
    }
  });

  it("drops slugs that fail digigraph's rule even when they are not house look-alikes", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const raw = JSON.stringify({ "-lead": EVIL, "a_b": EVIL, "a.b": EVIL, "a b": EVIL, "tenant-b": PINNED });
    const out = JSON.parse(composeCorpusMapWithKv(HOUSE, LEGACY, raw));
    expect(Object.keys(out)).toEqual(["digithings", "digithings-ai", "tenant-a", "tenant-b"]);
    expect(warn).toHaveBeenCalledTimes(4);
  });

  it("logs a hash tag and a reason, never the rejected slug itself", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const raw = JSON.stringify({
      "Secret-Client": EVIL,
      " secret-client": EVIL,
      "\u001csecret-client-two": EVIL,
      DIGITHINGS: EVIL,
    });
    composeCorpusMapWithKv(HOUSE, LEGACY, raw);
    const logged = warn.mock.calls.map((c) => c.map(String).join(" ")).join("\n");
    expect(logged.toLowerCase()).not.toContain("secret-client");
    expect(logged.toLowerCase()).not.toContain("digithings\"");
    expect(logged).toMatch(/#[0-9a-f]{8}/);
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
