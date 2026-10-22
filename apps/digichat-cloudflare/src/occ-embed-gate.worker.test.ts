/**
 * Worker-level check for the /embed invite gate: the key-bearing OCC embed
 * (the path 2.6.6 broke) still reaches the container untouched, and only the
 * keyless form gets the site 404. Container and Pages are mocked.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const KEY = "fixture-invite-key";
const containerFetch = vi.fn(async (req: Request) => {
  const url = new URL(req.url);
  return new Response("<!doctype html><title>digichat</title>", {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      // What a healthy container answers: a relative rewrite (2.6.6 sent an absolute one).
      "x-middleware-rewrite": `${url.pathname}?host=occ.digithings.ai&layout=page`,
    },
  });
});

vi.mock("cloudflare:workers", () => ({ env: {} }));
vi.mock("@cloudflare/containers", () => ({
  Container: class {},
  getContainer: () => ({ fetch: containerFetch, destroy: async () => {} }),
}));

const pages = vi.fn(
  async () =>
    new Response("<title>Page not found</title>", {
      status: 404,
      headers: { "content-type": "text/html; charset=utf-8" },
    }),
);

beforeEach(() => {
  containerFetch.mockClear();
  pages.mockClear();
  vi.stubGlobal("fetch", pages);
});

async function worker() {
  return (await import("./index")).default;
}

const env = { OCC_INVITE_KEY: KEY } as never;

describe("the /embed invite gate in the Worker", () => {
  it("passes the key-bearing OCC embed to the container: 200 text/html, relative rewrite", async () => {
    const w = await worker();
    for (let i = 0; i < 3; i++) {
      const res = await w.fetch(
        new Request(`https://digithings.ai/embed?host=occ.digithings.ai&layout=page&token=${KEY}`),
        env,
      );
      expect(res.status).toBe(200);
      expect(res.headers.get("content-type")).toMatch(/^text\/html/);
      expect(res.headers.get("x-middleware-rewrite")).toMatch(/^\/embed\?/);
    }
    expect(containerFetch).toHaveBeenCalledTimes(3);
    const forwarded = new URL(containerFetch.mock.calls[0]![0].url);
    expect(forwarded.searchParams.get("token")).toBe(KEY);
    expect(pages).not.toHaveBeenCalled();
  });

  it("keeps the house embed ungated", async () => {
    const w = await worker();
    expect(
      (
        await w.fetch(
          new Request("https://digithings.ai/embed?host=digithings.ai&layout=page"),
          env,
        )
      ).status,
    ).toBe(200);
    expect(containerFetch).toHaveBeenCalledTimes(1);
  });

  it("answers the keyless or wrong-key OCC embed with the site 404, never the container", async () => {
    const w = await worker();
    for (const q of ["", "&token=wrong", "&token="]) {
      const res = await w.fetch(
        new Request(`https://digithings.ai/embed?host=occ.digithings.ai&layout=page${q}`),
        env,
      );
      expect(res.status).toBe(404);
      expect(await res.text()).not.toMatch(/occ|digichat/i);
    }
    expect(containerFetch).not.toHaveBeenCalled();
  });
  it("gates the Referer form, the port form, an encoded host, a subpath and a padded key", async () => {
    const w = await worker();
    const cases: Array<[string, Record<string, string>]> = [
      ["https://digithings.ai/embed?layout=page", { referer: "https://occ.digithings.ai/x" }],
      ["https://digithings.ai/embed?host=&layout=page", { referer: "https://occ.digithings.ai/" }],
      ["https://digithings.ai/embed?host=occ.digithings.ai:443", {}],
      ["https://digithings.ai/embed?host=occ%2Edigithings%2Eai", {}],
      ["https://digithings.ai/embed/x?host=occ.digithings.ai", {}],
    ];
    for (const [u, headers] of cases) {
      const res = await w.fetch(new Request(u, { headers }), env);
      expect(res.status, u).toBe(404);
    }
    expect(containerFetch).not.toHaveBeenCalled();
    const padded = await w.fetch(
      new Request(`https://digithings.ai/embed?host=occ.digithings.ai&token=%20${KEY}%20`),
      env,
    );
    expect(padded.status).toBe(200);
  });

  it("fails closed when the Worker secret is unset", async () => {
    const w = await worker();
    const res = await w.fetch(
      new Request(`https://digithings.ai/embed?host=occ.digithings.ai&token=${KEY}`),
      {} as never,
    );
    expect(res.status).toBe(404);
    expect(containerFetch).not.toHaveBeenCalled();
  });
});
