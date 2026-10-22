/**
 * Worker-level check for the /embed invite gate: the key-bearing OCC embed
 * (the path 2.6.6 broke) still reaches the container untouched, and only the
 * keyless form gets the site 404. Container and Pages are mocked.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { containerPathFor } from "./paths";

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
      // The container's own relative rewrite, passed through untouched: 2.6.6
      // sent an absolute one. The container path is read back from the
      // forwarded request, so this holds wherever the embed route lives.
      const rewrite = res.headers.get("x-middleware-rewrite") ?? "";
      expect(rewrite).not.toMatch(/^https?:\/\//);
      expect(rewrite.startsWith("/")).toBe(true);
      const forwardedPath = new URL(containerFetch.mock.calls[i]![0].url).pathname;
      expect(forwardedPath).toBe(containerPathFor("/embed"));
      expect(rewrite).toBe(`${containerPathFor("/embed")}?host=occ.digithings.ai&layout=page`);
    }
    expect(containerFetch).toHaveBeenCalledTimes(3);
    const forwarded = new URL(containerFetch.mock.calls[0]![0].url);
    expect(forwarded.searchParams.get("token")).toBe(KEY);
    expect(pages).not.toHaveBeenCalled();
  });

  it("gates the base-path spelling of the OCC embed too (DIG-5121)", async () => {
    const w = await worker();
    // The keyless form gets the site 404 and never reaches the container.
    for (const path of [
      "/chat/embed?host=occ.digithings.ai&layout=page",
      "/chat/embed/x?host=occ.digithings.ai",
      "/chat/?mode=embed&host=occ.digithings.ai&layout=page",
    ]) {
      const res = await w.fetch(new Request(`https://digithings.ai${path}`), env);
      expect(res.status, path).toBe(404);
      expect(await res.text()).not.toMatch(/occ|digichat/i);
    }
    expect(containerFetch).not.toHaveBeenCalled();
    // The key-bearing form reaches the container, on the base-path route.
    const ok = await w.fetch(
      new Request(
        `https://digithings.ai/chat/embed?host=occ.digithings.ai&layout=page&token=${KEY}`,
      ),
      env,
    );
    expect(ok.status).toBe(200);
    expect(containerFetch).toHaveBeenCalledTimes(1);
    expect(new URL(containerFetch.mock.calls[0]![0].url).pathname).toBe(containerPathFor("/embed"));
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
