import { describe, expect, it } from "vitest";
import type { Env } from "./env";
import { handleFetch } from "./http";

function env(overrides: Partial<Env> = {}): Env {
  return overrides as Env;
}

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

describe("POST /embed", () => {
  const ai = { run: async (_m: unknown, input: { text: string[] }) => ({ data: input.text.map(() => new Array(1024).fill(0.1)) }) };
  const env = (secret?: string) => ({ EMBED_SECRET: secret, AI: ai }) as never;
  const req = (auth: string, body: unknown) =>
    new Request("https://x/embed", { method: "POST", headers: { Authorization: auth }, body: JSON.stringify(body) });
  const noop = async () => {};
  it("404 without a secret, 401 with a wrong one", async () => {
    expect((await handleFetch(req("Bearer s", { text: ["a"] }), env(), noop)).status).toBe(404);
    expect((await handleFetch(req("Bearer nope", { text: ["a"] }), env("s"), noop)).status).toBe(401);
  });
  it("returns 1024-dim rows in the Workers AI shape", async () => {
    const res = await handleFetch(req("Bearer s", { text: ["a", "b"] }), env("s"), noop);
    const body = (await res.json()) as { result: { data: number[][] } };
    expect(body.result.data).toHaveLength(2);
    expect(body.result.data[0]).toHaveLength(1024);
  });
  it("rejects bad input", async () => {
    expect((await handleFetch(req("Bearer s", { text: [] }), env("s"), noop)).status).toBe(400);
  });
});
