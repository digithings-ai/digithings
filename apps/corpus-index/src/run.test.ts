import { afterEach, describe, expect, it, vi } from "vitest";
import type { Env } from "./env";
import { runIndex } from "./run";

const NOW = new Date("2026-10-19T03:00:00.000Z");
const HOUR = 60 * 60 * 1000;

function memoryKv(seed: Record<string, string> = {}) {
  const data = new Map(Object.entries(seed));
  return {
    data,
    get: async (key: string) => data.get(key) ?? null,
    put: async (key: string, value: string) => {
      data.set(key, value);
    },
    delete: async (key: string) => {
      data.delete(key);
    },
  };
}

const job = {
  id: "occ",
  zammadBaseUrl: "https://support.example",
  siteUrl: "https://help.example",
  helpIndex: "help-m3",
  ticketsIndex: "tickets-m3",
  skipInternal: true,
};

function fakeFetch(url: string): Response {
  if (url.includes("/api/v1/tickets/search")) {
    return Response.json({ tickets: [] });
  }
  if (url === "https://help.example/sitemap.xml") {
    return new Response("<urlset></urlset>", {
      headers: { "content-type": "application/xml" },
    });
  }
  return new Response("not found", { status: 404 });
}

function seed(hoursAgo: number | null): Record<string, string> {
  const record: Record<string, string> = {
    "corpus-index:jobs": JSON.stringify([job]),
  };
  if (hoursAgo !== null) {
    const stamp = new Date(NOW.getTime() - hoursAgo * HOUR).toISOString();
    record["corpus-index:state:occ:tickets"] = JSON.stringify({
      lastSuccessAt: stamp,
      newestTicketAt: stamp,
      tickets: 1,
      vectors: 1,
      deleted: 0,
    });
  }
  return record;
}

function run(seedRecord: Record<string, string>) {
  const kv = memoryKv(seedRecord);
  const env = {
    CORPUS_INDEX_KV: kv,
    ZAMMAD_API_TOKEN: "test-token",
    CLOUDFLARE_ACCOUNT_ID: "account",
    CLOUDFLARE_API_TOKEN: "vectorize-token",
    AI: { run: async () => ({ data: [] }) },
    DRY_RUN: "0",
  } as unknown as Env;
  const lines: string[] = [];
  const spy = vi.spyOn(console, "log").mockImplementation((line: unknown) => {
    lines.push(String(line));
  });
  return { kv, lines, spy, promise: runIndex(env, NOW) };
}

function events(lines: string[]): Record<string, unknown>[] {
  return lines.map((line) => JSON.parse(line) as Record<string, unknown>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("runIndex freshness", () => {
  it("alerts before the sync when the previous success is past the threshold", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => fakeFetch(String(input)));
    const { lines, promise } = run(seed(40));
    await promise;
    const stale = events(lines).filter((row) => row.event === "corpus_index_stale");
    expect(stale).toHaveLength(1);
    expect(stale[0].job).toBe("occ");
    expect(stale[0].reason).toBe("stale_last_success");
  });

  it("does not alert when the previous success is inside the threshold", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => fakeFetch(String(input)));
    const { lines, promise } = run(seed(24));
    await promise;
    expect(events(lines).some((row) => row.event === "corpus_index_stale")).toBe(false);
    const freshness = events(lines).find((row) => row.event === "corpus_index_freshness");
    expect(freshness?.alert).toBe(false);
  });

  it("alerts when the job has never succeeded", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => fakeFetch(String(input)));
    const { lines, promise } = run(seed(null));
    await promise;
    const stale = events(lines).filter((row) => row.event === "corpus_index_stale");
    expect(stale[0].reason).toBe("never_succeeded");
  });

  it("writes a success stamp after the pass", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => fakeFetch(String(input)));
    const { kv, promise } = run(seed(40));
    await promise;
    const state = JSON.parse(kv.data.get("corpus-index:state:occ:tickets") ?? "{}");
    expect(state.lastSuccessAt).toBe(NOW.toISOString());
  });
});
