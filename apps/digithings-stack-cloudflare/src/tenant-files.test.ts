import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  applyTenantFilesEnv,
  readTenantFilesEnv,
  CONTAINER_ENV_VAR_MAX_BYTES,
  TENANT_FILES_CHUNK,
  TENANT_FILES_MAX_B64,
  TENANT_FILES_MAX_PARTS,
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

  it("keeps every generated env var under the container per-variable limit", () => {
    // Bytes as the runtime sees them: name, "=" and value.
    const bytes = (k: string, v: string) => Buffer.byteLength(`${k}=${v}`, "utf8");
    expect(TENANT_FILES_CHUNK).toBeLessThan(CONTAINER_ENV_VAR_MAX_BYTES);
    for (const size of [4, TENANT_FILES_CHUNK, TENANT_FILES_CHUNK + 4, 167_496, TENANT_FILES_MAX_B64]) {
      const bundle = "A".repeat(size - (size % 4));
      const env = tenantFilesEnv(doc(bundle));
      const parts = Number(env.DIGI_TENANT_FILES_PARTS);
      expect(parts).toBe(Math.ceil(bundle.length / TENANT_FILES_CHUNK));
      expect(parts).toBeLessThanOrEqual(TENANT_FILES_MAX_PARTS);
      let joined = "";
      for (let i = 0; i < parts; i += 1) joined += env[`DIGI_TENANT_FILES_${i}`];
      expect(joined).toBe(bundle);
      for (const [k, v] of Object.entries(env)) {
        expect(bytes(k, v)).toBeLessThan(CONTAINER_ENV_VAR_MAX_BYTES);
      }
    }
  });

  it("refuses a bundle the container unpacker would reject for its part count", () => {
    const over = "A".repeat(TENANT_FILES_MAX_B64 + 4);
    expect(tenantFilesEnv(doc(over))).toEqual({});
  });

  it("matches the part ceiling container/unpack_tenant_files.py enforces", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const unpacker = readFileSync(join(here, "../container/unpack_tenant_files.py"), "utf8");
    expect(unpacker).toContain(`parts > ${TENANT_FILES_MAX_PARTS}:`);
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

  it("replaces stale tenant-files env and leaves every other var alone", () => {
    const target: Record<string, string> = {
      DIGI_TENANT_FILES_0: "old0",
      DIGI_TENANT_FILES_1: "old1",
      DIGI_TENANT_FILES_2: "old2",
      DIGI_TENANT_FILES_PARTS: "3",
      DIGIGRAPH_WEB_SEARCH_SITES_DIR: "/data/tenant-files/sites",
      DIGISEARCH_PAGE_CORPUS_DIR: "/data/tenant-files/pages",
      DIGI_TENANT_FILES_NOTE: "not owned",
      OTHER: "kept",
    };
    const fresh = tenantFilesEnv(doc("QUJD"));
    applyTenantFilesEnv(target, fresh);
    expect(target.DIGI_TENANT_FILES_0).toBe("QUJD");
    expect(target.DIGI_TENANT_FILES_PARTS).toBe("1");
    expect("DIGI_TENANT_FILES_1" in target).toBe(false);
    expect("DIGI_TENANT_FILES_2" in target).toBe(false);
    expect(target.OTHER).toBe("kept");
    expect(target.DIGI_TENANT_FILES_NOTE).toBe("not owned");
    // A removed bundle clears every owned key.
    applyTenantFilesEnv(target, {});
    expect(target).toEqual({ DIGI_TENANT_FILES_NOTE: "not owned", OTHER: "kept" });
  });
});
