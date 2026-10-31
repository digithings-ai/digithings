import { describe, expect, it } from "vitest";
import {
  addGatedClaims,
  CONFIG_KV_KEY,
  GATED_CLAIMS_KV_KEY,
  parseGatedClaims,
  resolveGatedClaims,
  TENANTS_KV_KEY,
  unionGatedClaims,
} from "./tenants-kv";

const A = { slug: "example", chatSlug: "example", host: "example.digithings.test" };
const B = { slug: "example-b", chatSlug: "example-b", host: "b.example.com" };

describe("gated-claims KV key", () => {
  it("is its own key in the tenants namespace", () => {
    expect(GATED_CLAIMS_KV_KEY).toBe("gated-claims");
    expect(GATED_CLAIMS_KV_KEY).not.toBe(TENANTS_KV_KEY);
    expect(GATED_CLAIMS_KV_KEY).not.toBe(CONFIG_KV_KEY);
  });
});

describe("parseGatedClaims", () => {
  it("normalizes valid rows and lowercases", () => {
    expect(parseGatedClaims(JSON.stringify([{ slug: "Example", chatSlug: "EXAMPLE", host: "Example.Digithings.Test" }]))).toEqual([A]);
  });
  it("skips bad rows one by one and keeps the good ones", () => {
    const raw = JSON.stringify([
      A,
      { slug: "bad slug", chatSlug: "x", host: "x.example.com" },
      { slug: "nohost" },
      { slug: "x", chatSlug: "x", host: "not a host" },
      "string",
      null,
      B,
    ]);
    expect(parseGatedClaims(raw)).toEqual([A, B]);
  });
  it("dedupes on chatSlug|host, first wins", () => {
    expect(parseGatedClaims(JSON.stringify([A, { ...A, slug: "other" }]))).toEqual([A]);
  });
  it("yields nothing for empty, non-JSON or non-array values", () => {
    for (const raw of [undefined, null, "", "  ", "{", "{}", '"x"', "42"]) {
      expect(parseGatedClaims(raw as string | null | undefined)).toEqual([]);
    }
  });
  it("accepts a host-only or slug-only claim", () => {
    expect(parseGatedClaims(JSON.stringify([{ slug: "h", host: "h.example.com" }]))).toEqual([
      { slug: "h", chatSlug: "", host: "h.example.com" },
    ]);
    expect(parseGatedClaims(JSON.stringify([{ slug: "s", chatSlug: "s" }]))).toEqual([{ slug: "s", chatSlug: "s" }]);
  });
});

describe("addGatedClaims (writer, add-only)", () => {
  it("creates the list when the key is missing", () => {
    expect(JSON.parse(addGatedClaims(null, [A]))).toEqual([A]);
  });
  it("keeps every existing claim and appends only new keys", () => {
    const next = addGatedClaims(JSON.stringify([A]), [A, B]);
    expect(JSON.parse(next)).toEqual([A, B]);
  });
  it("never drops a claim, whatever the add list is", () => {
    expect(JSON.parse(addGatedClaims(JSON.stringify([A, B]), []))).toEqual([A, B]);
  });
  it("refuses to overwrite a value it cannot read", () => {
    expect(() => addGatedClaims("{not json", [B])).toThrow(/refusing/);
    expect(() => addGatedClaims("{}", [B])).toThrow(/refusing/);
    expect(() => addGatedClaims(JSON.stringify([A, { slug: "bad slug" }]), [B])).toThrow(/by hand/);
  });
  it("refuses an invalid new claim", () => {
    expect(() => addGatedClaims(JSON.stringify([A]), [{ slug: "x" }])).toThrow(/invalid claim/);
  });
});

describe("unionGatedClaims", () => {
  it("keeps the first of each key across lists", () => {
    expect(unionGatedClaims([A], [{ ...A, slug: "later" }, B], [])).toEqual([A, B]);
  });
});

describe("resolveGatedClaims", () => {
  it("reads and normalizes the KV value", async () => {
    const kv = { get: async (k: string) => (k === GATED_CLAIMS_KV_KEY ? JSON.stringify([A, { bad: 1 }]) : null) };
    const r = await resolveGatedClaims(kv);
    expect(r.source).toBe("kv");
    expect(r.claims).toEqual([A]);
    expect(JSON.parse(r.json)).toEqual([A]);
  });
  it("is none for a missing binding, key or blank value", async () => {
    await expect(resolveGatedClaims(undefined)).resolves.toMatchObject({ source: "none", json: "" });
    await expect(resolveGatedClaims({ get: async () => null })).resolves.toMatchObject({ source: "none", json: "" });
    await expect(resolveGatedClaims({ get: async () => " " })).resolves.toMatchObject({ source: "none", json: "" });
  });
  it("is error (never throws) when the read fails", async () => {
    const kv = { get: async () => { throw new Error("kv down"); } };
    await expect(resolveGatedClaims(kv)).resolves.toMatchObject({ source: "error", claims: [] });
  });
});
