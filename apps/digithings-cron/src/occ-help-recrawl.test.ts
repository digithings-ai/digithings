import { describe, expect, it } from "vitest";
import {
  FRESHNESS_ALERT_AFTER_DAYS,
  diffDocs,
  freshnessAlert,
  hashContent,
  newestDocAt,
  runRecrawl,
  type CrawledDoc,
  type RecrawlStore,
  type StoredDoc,
} from "./occ-help-recrawl";

const DAY_MS = 24 * 60 * 60 * 1000;

function crawled(url: string, text: string, updatedAt = "2026-10-12T00:00:00.000Z"): CrawledDoc {
  return { url, text, updatedAt };
}

function memoryStore(seed: StoredDoc[] = [], lastSuccessAt: string | null = null): RecrawlStore & {
  writes: string[];
} {
  const rows = new Map(seed.map((doc) => [doc.url, doc.contentHash]));
  let state = { lastSuccessAt };
  const writes: string[] = [];
  return {
    writes,
    list: () => [...rows].map(([url, contentHash]) => ({ url, contentHash })),
    upsert: (doc) => {
      writes.push(`upsert:${doc.url}`);
      rows.set(doc.url, doc.contentHash);
    },
    remove: (url) => {
      writes.push(`remove:${url}`);
      rows.delete(url);
    },
    getState: () => ({ ...state }),
    putState: (next) => {
      writes.push("putState");
      state = { ...next };
    },
  };
}

describe("hashContent", () => {
  it("is stable and changes with the text", () => {
    expect(hashContent("hello")).toBe(hashContent("hello"));
    expect(hashContent("hello")).not.toBe(hashContent("hello!"));
  });
});

describe("diffDocs", () => {
  it("upserts new and changed docs and deletes docs gone from source", () => {
    const source = [crawled("https://h/a", "new"), crawled("https://h/b", "changed")];
    const stored: StoredDoc[] = [
      { url: "https://h/b", contentHash: hashContent("old") },
      { url: "https://h/gone", contentHash: hashContent("x") },
    ];
    const { upserts, deletes } = diffDocs(source, stored);
    expect(upserts.map((doc) => doc.url).sort()).toEqual(["https://h/a", "https://h/b"]);
    expect(deletes).toEqual(["https://h/gone"]);
  });

  it("is empty when source matches the store", () => {
    const source = [crawled("https://h/a", "same")];
    const stored: StoredDoc[] = [{ url: "https://h/a", contentHash: hashContent("same") }];
    expect(diffDocs(source, stored)).toEqual({ upserts: [], deletes: [] });
  });
});

describe("runRecrawl", () => {
  it("writes nothing on a re-run with unchanged source", async () => {
    const source = [crawled("https://h/a", "body")];
    const first = memoryStore([], "2026-10-12T00:00:00.000Z");
    const one = await runRecrawl(source, first, { nowMs: Date.parse("2026-10-19T00:00:00.000Z") });
    expect(one.wrote).toBe(true);
    const second = memoryStore(
      [{ url: "https://h/a", contentHash: hashContent("body") }],
      one.metric.lastSuccessAt,
    );
    const two = await runRecrawl(source, second, { nowMs: Date.parse("2026-10-19T01:00:00.000Z") });
    expect(two).toMatchObject({ upserted: 0, deleted: 0, wrote: false });
    expect(second.writes).toEqual([]);
    expect(two.metric.rowsChanged).toBe(0);
  });

  it("dry-run reports the diff and writes nothing", async () => {
    const source = [crawled("https://h/a", "body")];
    const store = memoryStore();
    const result = await runRecrawl(source, store, { dryRun: true });
    expect(result).toMatchObject({ upserted: 1, wrote: false, dryRun: true });
    expect(store.writes).toEqual([]);
  });

  it("records the freshness metric on a write", async () => {
    const source = [
      crawled("https://h/a", "one", "2026-10-10T00:00:00.000Z"),
      crawled("https://h/b", "two", "2026-10-12T00:00:00.000Z"),
    ];
    const store = memoryStore();
    const result = await runRecrawl(source, store, { nowMs: Date.parse("2026-10-19T00:00:00.000Z") });
    expect(result.metric).toMatchObject({
      lastSuccessAt: "2026-10-19T00:00:00.000Z",
      newestDocAt: "2026-10-12T00:00:00.000Z",
      rowsChanged: 2,
      rowsTotal: 2,
    });
  });
});

describe("newestDocAt", () => {
  it("returns null for an empty source", () => {
    expect(newestDocAt([])).toBeNull();
  });
});

describe("freshnessAlert", () => {
  const base = { newestDocAt: "2026-10-12T00:00:00.000Z", rowsChanged: 0, rowsTotal: 5 };

  it("alerts when nothing ever succeeded", () => {
    expect(freshnessAlert({ ...base, lastSuccessAt: null }, Date.parse("2026-10-19T00:00:00.000Z"))).toMatchObject({
      alert: true,
      reason: "never_succeeded",
    });
  });

  it("stays quiet at exactly the threshold and alerts past it", () => {
    const last = "2026-10-11T00:00:00.000Z";
    const at = Date.parse(last) + FRESHNESS_ALERT_AFTER_DAYS * DAY_MS;
    expect(freshnessAlert({ ...base, lastSuccessAt: last }, at).alert).toBe(false);
    expect(freshnessAlert({ ...base, lastSuccessAt: last }, at + 1000)).toMatchObject({
      alert: true,
      reason: "stale_last_success",
    });
  });

  it("alerts on an unparseable last success", () => {
    expect(freshnessAlert({ ...base, lastSuccessAt: "not-a-date" }, Date.now()).alert).toBe(true);
  });
});
