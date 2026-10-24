import { describe, expect, it } from "vitest";
import type { Env } from "./env";
import { handleFetch } from "./http";

function env(overrides: Partial<Env> = {}): Env {
  return overrides as Env;
}

function memoryKv(seed: Record<string, string> = {}): KVNamespace {
  const data = new Map(Object.entries(seed));
  return { get: async (key: string) => data.get(key) ?? null } as unknown as KVNamespace;
}

const job = {
  id: "occ",
  zammadBaseUrl: "https://support.example",
  siteUrl: "https://help.example",
  helpIndex: "help-m3",
  ticketsIndex: "tickets-m3",
  skipInternal: true,
};

describe("handleFetch", () => {
  it("answers health without job config", async () => {
    const response = await handleFetch(
      new Request("https://corpus-index/healthz"),
      env(),
      async () => {},
    );
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toEqual({ ok: true, service: "corpus-index", dry_run: false });
  });

  it("returns 404 for a chat path and for /run when the kick secret is unset", async () => {
    const chat = await handleFetch(new Request("https://corpus-index/chat/occ"), env(), async () => {});
    expect(chat.status).toBe(404);
    const closed = await handleFetch(
      new Request("https://corpus-index/run", { method: "POST" }),
      env(),
      async () => {},
    );
    expect(closed.status).toBe(404);
  });

  it("returns 401 for a wrong key and starts a run for the right key", async () => {
    let started = 0;
    const wrong = await handleFetch(
      new Request("https://corpus-index/run", {
        method: "POST",
        headers: { Authorization: "Bearer wrong-key" },
      }),
      env({ CRON_KICK_SECRET: "right-key" }),
      async () => {
        started += 1;
      },
    );
    expect(wrong.status).toBe(401);
    expect(started).toBe(0);
    const right = await handleFetch(
      new Request("https://corpus-index/run", {
        method: "POST",
        headers: { Authorization: "Bearer right-key" },
      }),
      env({ CRON_KICK_SECRET: "right-key" }),
      async () => {
        started += 1;
      },
    );
    expect(right.status).toBe(200);
    expect(started).toBe(1);
    const payload = await right.json();
    expect(payload).toEqual({ ok: true, started: true });
  });
});

describe("GET /freshness", () => {
  const seed = (overrides: Record<string, string> = {}) => {
    const recent = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    return memoryKv({
      "corpus-index:jobs": JSON.stringify([job]),
      "corpus-index:state:occ:tickets": JSON.stringify({
        lastSuccessAt: recent,
        newestTicketAt: recent,
        tickets: 2,
        vectors: 2,
        deleted: 0,
      }),
      ...overrides,
    });
  };

  it("is closed when the kick secret is unset", async () => {
    const response = await handleFetch(
      new Request("https://corpus-index/freshness"),
      env({ CORPUS_INDEX_KV: seed() }),
      async () => {},
    );
    expect(response.status).toBe(404);
  });

  it("rejects a wrong key", async () => {
    const response = await handleFetch(
      new Request("https://corpus-index/freshness", {
        headers: { Authorization: "Bearer wrong-key" },
      }),
      env({ CORPUS_INDEX_KV: seed(), CRON_KICK_SECRET: "right-key" }),
      async () => {},
    );
    expect(response.status).toBe(401);
  });

  it("reports a fresh job and a stale one", async () => {
    const old = new Date(Date.now() - 40 * 60 * 60 * 1000).toISOString();
    const response = await handleFetch(
      new Request("https://corpus-index/freshness", {
        headers: { Authorization: "Bearer right-key" },
      }),
      env({
        CORPUS_INDEX_KV: seed({
          "corpus-index:state:occ:tickets": JSON.stringify({
            lastSuccessAt: old,
            newestTicketAt: old,
            tickets: 2,
            vectors: 2,
            deleted: 0,
          }),
        }),
        CRON_KICK_SECRET: "right-key",
      }),
      async () => {},
    );
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.ok).toBe(true);
    expect(body.jobs).toHaveLength(1);
    expect(body.jobs[0].job).toBe("occ");
    expect(body.jobs[0].alert).toBe(true);
    expect(body.jobs[0].reason).toBe("stale_last_success");
  });

  it("reports fresh state as no alert", async () => {
    const response = await handleFetch(
      new Request("https://corpus-index/freshness", {
        headers: { Authorization: "Bearer right-key" },
      }),
      env({ CORPUS_INDEX_KV: seed(), CRON_KICK_SECRET: "right-key" }),
      async () => {},
    );
    const body = await response.json();
    expect(body.jobs[0].alert).toBe(false);
    expect(body.jobs[0].reason).toBe("fresh");
  });

  it("returns an empty list when no job is configured", async () => {
    const response = await handleFetch(
      new Request("https://corpus-index/freshness", {
        headers: { Authorization: "Bearer right-key" },
      }),
      env({ CORPUS_INDEX_KV: memoryKv(), CRON_KICK_SECRET: "right-key" }),
      async () => {},
    );
    const body = await response.json();
    expect(body).toEqual({ ok: true, jobs: [] });
  });
});
