import { describe, expect, it } from "vitest";
import {
  readTenantFilesEnv,
  TENANT_FILES_CHUNK,
  TENANT_FILES_KEY,
  tenantFilesEnv,
} from "./tenant-files";

const doc = (bundle: string, v: unknown = 1) => JSON.stringify({ v, bundle });

describe("tenant files env", () => {
  it("is empty for an absent, blank, malformed or wrong-shape value", () => {
    for (const raw of [null, undefined, "", "  ", "{", "[]", doc("abc=", 2), JSON.stringify({ v: 1 })]) {
      expect(tenantFilesEnv(raw as string | null)).toEqual({});
    }
  });

  it("refuses a bundle that is not base64", () => {
    expect(tenantFilesEnv(doc("not base64!"))).toEqual({});
    expect(tenantFilesEnv(doc("a b"))).toEqual({});
  });

  it("chunks the bundle and names both reader directories", () => {
    const bundle = "A".repeat(TENANT_FILES_CHUNK * 2 + 5);
    const env = tenantFilesEnv(doc(bundle));
    expect(env.DIGI_TENANT_FILES_PARTS).toBe("3");
    expect(env.DIGI_TENANT_FILES_0 + env.DIGI_TENANT_FILES_1 + env.DIGI_TENANT_FILES_2).toBe(bundle);
    expect(env.DIGIGRAPH_WEB_SEARCH_SITES_DIR).toBe("/data/tenant-files/sites");
    expect(env.DIGISEARCH_PAGE_CORPUS_DIR).toBe("/data/tenant-files/pages");
  });

  it("reads the one key and treats a KV failure as no files", async () => {
    const seen: string[] = [];
    const ok = { get: async (k: string) => (seen.push(k), doc("QUJD")) };
    expect((await readTenantFilesEnv(ok)).DIGI_TENANT_FILES_0).toBe("QUJD");
    expect(seen).toEqual([TENANT_FILES_KEY]);
    const boom = { get: async () => { throw new Error("kv down"); } };
    expect(await readTenantFilesEnv(boom)).toEqual({});
    expect(await readTenantFilesEnv(undefined)).toEqual({});
  });
});
