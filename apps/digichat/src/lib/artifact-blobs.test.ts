import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  createFileBlobStore,
  createR2BlobStore,
  defaultFileBlobRoot,
  isSafeBlobKey,
  type R2Like,
} from "./artifact-blobs";

/** An in-memory R2 stand-in with the same surface a Worker binding exposes. */
function fakeBucket(): R2Like & { store: Map<string, Uint8Array> } {
  const store = new Map<string, Uint8Array>();
  return {
    store,
    async put(key, value) {
      store.set(key, new Uint8Array(value as Uint8Array));
      return { key };
    },
    async get(key) {
      const found = store.get(key);
      if (!found) return null;
      return { arrayBuffer: async () => found.buffer.slice(0) };
    },
    async delete(key) {
      store.delete(key);
    },
  };
}

describe("artifact blob keys", () => {
  it("accepts an opaque generated key", () => {
    expect(isSafeBlobKey("artifacts/conv-1/abc123")).toBe(true);
    expect(isSafeBlobKey("artifacts/conv-1/abc-123_x.json")).toBe(true);
  });

  it("rejects traversal, empty segments and control characters", () => {
    expect(isSafeBlobKey("../etc/passwd")).toBe(false);
    expect(isSafeBlobKey("artifacts/../../etc/passwd")).toBe(false);
    expect(isSafeBlobKey("artifacts//conv")).toBe(false);
    expect(isSafeBlobKey("artifacts/./conv")).toBe(false);
    expect(isSafeBlobKey("")).toBe(false);
    expect(isSafeBlobKey("a\0b")).toBe(false);
    expect(isSafeBlobKey("a b")).toBe(false);
  });
});

describe("R2 blob store", () => {
  it("round-trips bytes", async () => {
    const bucket = fakeBucket();
    const store = createR2BlobStore(bucket);
    await store.put("artifacts/conv-1/tok", new Uint8Array([1, 2, 3]), "text/csv");
    const got = await store.get("artifacts/conv-1/tok");
    expect(Array.from(got ?? [])).toEqual([1, 2, 3]);
  });

  it("returns null for a missing key rather than throwing", async () => {
    const store = createR2BlobStore(fakeBucket());
    expect(await store.get("artifacts/conv-1/nope")).toBeNull();
  });

  it("deletes", async () => {
    const bucket = fakeBucket();
    const store = createR2BlobStore(bucket);
    await store.put("artifacts/conv-1/tok", new Uint8Array([1]), "text/csv");
    await store.delete("artifacts/conv-1/tok");
    expect(await store.get("artifacts/conv-1/tok")).toBeNull();
  });

  it("refuses an unsafe key on every operation", async () => {
    const store = createR2BlobStore(fakeBucket());
    await expect(store.put("../escape", new Uint8Array([1]), "text/plain")).rejects.toThrow();
    await expect(store.get("../escape")).rejects.toThrow();
    await expect(store.delete("../escape")).rejects.toThrow();
  });

  it("rejects a bucket missing the methods we use", () => {
    expect(() => createR2BlobStore({} as unknown as R2Like)).toThrow();
  });
});

describe("filesystem blob store", () => {
  let root = "";

  beforeEach(async () => {
    root = await mkdtemp(join(tmpdir(), "digichat-artifacts-"));
  });

  afterEach(async () => {
    await rm(root, { recursive: true, force: true });
  });

  it("round-trips bytes and creates nested directories", async () => {
    const store = createFileBlobStore(root);
    await store.put("artifacts/conv-1/tok", new Uint8Array([9, 8, 7]), "text/csv");
    const got = await store.get("artifacts/conv-1/tok");
    expect(Array.from(got ?? [])).toEqual([9, 8, 7]);
  });

  it("returns null for a missing key", async () => {
    const store = createFileBlobStore(root);
    expect(await store.get("artifacts/conv-1/nope")).toBeNull();
  });

  it("delete is idempotent", async () => {
    const store = createFileBlobStore(root);
    await store.put("artifacts/conv-1/tok", new Uint8Array([1]), "text/csv");
    await store.delete("artifacts/conv-1/tok");
    await store.delete("artifacts/conv-1/tok");
    expect(await store.get("artifacts/conv-1/tok")).toBeNull();
  });

  it("never writes outside the root", async () => {
    const store = createFileBlobStore(root);
    await expect(store.put("../escape", new Uint8Array([1]), "text/plain")).rejects.toThrow();
    await expect(store.put("/etc/escape", new Uint8Array([1]), "text/plain")).rejects.toThrow();
  });

  it("rejects an empty root", () => {
    expect(() => createFileBlobStore("  ")).toThrow();
  });
});

describe("default filesystem root", () => {
  it("honours the explicit directory", () => {
    expect(defaultFileBlobRoot({ DIGICHAT_ARTIFACT_DIR: "/data/artifacts" })).toBe("/data/artifacts");
  });

  it("falls back to a path outside the image layers", () => {
    expect(defaultFileBlobRoot({})).toBe("/var/tmp/digichat-artifacts");
  });

  it("ignores a blank override", () => {
    expect(defaultFileBlobRoot({ DIGICHAT_ARTIFACT_DIR: "   " })).toBe("/var/tmp/digichat-artifacts");
  });
});
