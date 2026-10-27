import { describe, expect, it } from "vitest";
import { authenticate, hashToken, parseTokenRecord, tokenKey } from "./auth";
import { fakeKv } from "../test/fakes";

const TOKEN = "ingest-token-for-tests";

async function kvWith(record: Record<string, unknown>): Promise<ReturnType<typeof fakeKv>> {
  return fakeKv({ [await tokenKey(TOKEN)]: JSON.stringify(record) });
}

describe("hashToken", () => {
  it("returns a lowercase hex SHA-256", async () => {
    const digest = await hashToken(TOKEN);
    expect(digest).toMatch(/^[0-9a-f]{64}$/);
    // The known digest of the empty string pins the algorithm and the encoding.
    expect(await hashToken("")).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });

  it("namespaces the KV key and never contains the token", async () => {
    const key = await tokenKey(TOKEN);
    expect(key.startsWith("tok:")).toBe(true);
    expect(key).not.toContain(TOKEN);
  });
});

describe("parseTokenRecord", () => {
  it("accepts a source and a tenant list", () => {
    expect(parseTokenRecord('{"source":"digitrace-digichat","tenants":["digithings"]}')).toEqual({
      source: "digitrace-digichat",
      tenants: ["digithings"],
    });
  });

  it("fails closed on anything that is not that record", () => {
    expect(parseTokenRecord("not json")).toBeUndefined();
    expect(parseTokenRecord("null")).toBeUndefined();
    expect(parseTokenRecord('{"tenants":["digithings"]}')).toBeUndefined();
    expect(parseTokenRecord('{"source":"","tenants":["digithings"]}')).toBeUndefined();
    expect(parseTokenRecord('{"source":"s"}')).toBeUndefined();
    expect(parseTokenRecord('{"source":"s","tenants":[]}')).toBeUndefined();
    expect(parseTokenRecord('{"source":"s","tenants":["Not A Slug"]}')).toBeUndefined();
    expect(parseTokenRecord('{"source":"s","tenants":["ok",7]}')).toBeUndefined();
    expect(parseTokenRecord(undefined)).toBeUndefined();
  });
});

describe("authenticate", () => {
  it("accepts a known token and a tenant it may claim", async () => {
    const kv = await kvWith({ source: "digitrace-digichat", tenants: ["digithings", "occ"] });
    const result = await authenticate(kv.namespace, TOKEN, "occ");
    expect(result).toEqual({
      ok: true,
      context: { tenant: "occ", source: "digitrace-digichat", tenantSlugVerified: false },
    });
  });

  it("looks the token up by digest, not by value", async () => {
    const kv = await kvWith({ source: "s", tenants: ["digithings"] });
    await authenticate(kv.namespace, TOKEN, "digithings");
    expect(kv.reads).toEqual([await tokenKey(TOKEN)]);
    expect(kv.reads[0]).not.toContain(TOKEN);
  });

  it("refuses a missing token with 401", async () => {
    const kv = await kvWith({ source: "s", tenants: ["digithings"] });
    expect(await authenticate(kv.namespace, null, "digithings")).toEqual({
      ok: false,
      status: 401,
      reason: "missing ingest token",
    });
    expect(await authenticate(kv.namespace, "   ", "digithings")).toMatchObject({ status: 401 });
  });

  it("refuses an unknown token with 401", async () => {
    const kv = await kvWith({ source: "s", tenants: ["digithings"] });
    const result = await authenticate(kv.namespace, "not-the-token", "digithings");
    expect(result).toMatchObject({ ok: false, status: 401, reason: "unknown ingest token" });
  });

  it("refuses a tenant the token may not claim, with 403", async () => {
    const kv = await kvWith({ source: "digitrace-digichat", tenants: ["digithings"] });
    expect(await authenticate(kv.namespace, TOKEN, "someone-else")).toEqual({
      ok: false,
      status: 403,
      reason: "tenant claim is not allowed for this token",
    });
  });

  it("refuses a missing or malformed tenant claim with 403", async () => {
    const kv = await kvWith({ source: "s", tenants: ["digithings"] });
    expect(await authenticate(kv.namespace, TOKEN, null)).toMatchObject({
      status: 403,
      reason: "missing tenant claim",
    });
    expect(await authenticate(kv.namespace, TOKEN, "Digithings")).toMatchObject({
      status: 403,
      reason: "malformed tenant claim",
    });
    expect(await authenticate(kv.namespace, TOKEN, "../digithings")).toMatchObject({
      status: 403,
      reason: "malformed tenant claim",
    });
  });

  it("does not echo the token in a refusal", async () => {
    const kv = await kvWith({ source: "s", tenants: ["digithings"] });
    const result = await authenticate(kv.namespace, "secret-token-value", "digithings");
    expect(JSON.stringify(result)).not.toContain("secret-token-value");
  });

  it("always reports the static-token claim as unverified", async () => {
    const kv = await kvWith({ source: "s", tenants: ["digithings"] });
    const result = await authenticate(kv.namespace, TOKEN, "digithings");
    expect(result.ok && result.context.tenantSlugVerified).toBe(false);
  });
});
