import { describe, expect, it, vi } from "vitest";
import {
  bindInvitePageApiCall,
  invitePageCookieValue,
  invitePageEmbedGate,
  invitePageFor,
  invitePageGate,
  invitePageKey,
  parseInvitePages,
  withoutInvitePageCookies,
} from "./invite-pages";
import { EMBED_HOST_HEADER, EMBED_TOKEN_HEADER, OCC_INVITE_DEFAULT_MAX_AGE_DAYS } from "./occ-gate";

const KEY = "example-invite-key-fixture";
const ENV = { EXAMPLE_INVITE_KEY: KEY, EXAMPLE_B_INVITE_KEY: "example-b-key-fixture" };
const RAW = JSON.stringify({
  example: { host: "example.test.digithings.ai", keyEnv: "EXAMPLE_INVITE_KEY" },
  "example-b": { host: "example-b.test.digithings.ai", keyEnv: "EXAMPLE_B_INVITE_KEY" },
});
const PAGES = parseInvitePages(RAW);
const PAGE = PAGES[0]!;
const NOW_MS = Date.UTC(2026, 9, 29, 12, 0, 0);
const POLICY = { maxAgeSeconds: OCC_INVITE_DEFAULT_MAX_AGE_DAYS * 86400, nowMs: NOW_MS };
const NOW_S = NOW_MS / 1000;

const notFound = vi.fn(async () => new Response("site 404", { status: 404, headers: { "x-site": "1" } }));
const container = vi.fn(async (req: Request) => new Response(`container ${new URL(req.url).pathname}${new URL(req.url).search}`, { status: 200 }));

describe("parseInvitePages", () => {
  it("reads valid entries", () => {
    expect(PAGES.map((p) => [p.slug, p.path, p.host, p.keyEnv, p.cookie])).toEqual([
      ["example", "/chat/example", "example.test.digithings.ai", "EXAMPLE_INVITE_KEY", "example_invite"],
      ["example-b", "/chat/example-b", "example-b.test.digithings.ai", "EXAMPLE_B_INVITE_KEY", "example-b_invite"],
    ]);
  });
  it("is empty for unset or malformed input and never throws", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(parseInvitePages(undefined)).toEqual([]);
    expect(parseInvitePages("not json")).toEqual([]);
    expect(parseInvitePages("[1]")).toEqual([]);
    err.mockRestore();
  });
  it("drops reserved, malformed, duplicate and forbidden entries", () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const pages = parseInvitePages(
      JSON.stringify({
        occ: { host: "a.digithings.ai", keyEnv: "A_KEY" },
        embed: { host: "b.digithings.ai", keyEnv: "B_KEY" },
        api: { host: "c.digithings.ai", keyEnv: "C_KEY" },
        "Bad/Slug": { host: "d.digithings.ai", keyEnv: "D_KEY" },
        good: { host: "e.digithings.ai", keyEnv: "E_KEY" },
        dup: { host: "e.digithings.ai", keyEnv: "F_KEY" },
        samekey: { host: "g.digithings.ai", keyEnv: "E_KEY" },
        steal: { host: "h.digithings.ai", keyEnv: "AUTH_SECRET" },
        occkey: { host: "i.digithings.ai", keyEnv: "OCC_INVITE_KEY" },
        nohost: { keyEnv: "J_KEY" },
      }),
    );
    expect(pages.map((p) => p.slug)).toEqual(["good"]);
    err.mockRestore();
  });
  it("matches whole path segments only", () => {
    expect(invitePageFor(PAGES, "/chat/example")?.slug).toBe("example");
    expect(invitePageFor(PAGES, "/chat/example/")?.slug).toBe("example");
    expect(invitePageFor(PAGES, "/chat/example-b/")?.slug).toBe("example-b");
    expect(invitePageFor(PAGES, "/chat/examplex")).toBeNull();
    expect(invitePageFor(PAGES, "/chat")).toBeNull();
  });
});

describe("invitePageGate", () => {
  const gate = (req: Request, key: string | undefined = KEY) =>
    invitePageGate(PAGE, PAGES, req, key, container, notFound, POLICY);

  it("answers the site 404 without an invite", async () => {
    const res = await gate(new Request("https://digithings.ai/chat/example/"));
    expect(res.status).toBe(404);
    expect(await res.text()).toBe("site 404");
    expect(container).not.toHaveBeenCalled();
  });
  it("answers the site 404 for a wrong token, and fails closed with no secret", async () => {
    expect((await gate(new Request("https://digithings.ai/chat/example?token=nope"))).status).toBe(404);
    expect(
      (await invitePageGate(PAGE, PAGES, new Request(`https://digithings.ai/chat/example?token=${KEY}`), undefined, container, notFound, POLICY)).status,
    ).toBe(404);
    expect(invitePageKey(PAGE, {})).toBeUndefined();
    expect(container).not.toHaveBeenCalled();
  });
  it("trades a valid token for a cookie and a clean 302", async () => {
    const res = await gate(new Request(`https://digithings.ai/chat/example?token=${KEY}`));
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("https://digithings.ai/chat/example/");
    const cookie = res.headers.get("set-cookie") ?? "";
    expect(cookie).toMatch(/^example_invite=v2\.\d+\./);
    expect(cookie).toContain("Path=/chat; Secure; HttpOnly; SameSite=Strict");
    expect(cookie).not.toContain(KEY);
  });
  it("proxies a valid cookie to the app's embed route for the tenant host", async () => {
    const value = await invitePageCookieValue(PAGE, KEY, NOW_S);
    container.mockClear();
    const res = await gate(
      new Request("https://digithings.ai/chat/example/", {
        headers: { cookie: `example_invite=${encodeURIComponent(value)}; other=1`, "x-digi-tenant": "spoof" },
      }),
    );
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("container /chat/embed?host=example.test.digithings.ai");
    const sent = container.mock.calls[0]![0];
    expect(sent.headers.get(EMBED_TOKEN_HEADER)).toBe(KEY);
    expect(sent.headers.get(EMBED_HOST_HEADER)).toBe("example.test.digithings.ai");
    expect(sent.headers.get("x-digi-tenant")).toBeNull();
    expect(sent.headers.get("cookie")).toBe("other=1");
  });
  it("refuses an expired, tampered, or other page's cookie", async () => {
    const old = await invitePageCookieValue(PAGE, KEY, NOW_S - 31 * 86400);
    const other = await invitePageCookieValue(PAGES[1]!, KEY, NOW_S);
    for (const v of [old, `${old}x`, other, KEY]) {
      const res = await gate(
        new Request("https://digithings.ai/chat/example/", { headers: { cookie: `example_invite=${v}` } }),
      );
      expect(res.status).toBe(404);
    }
  });
});

describe("bindInvitePageApiCall", () => {
  it("binds a page call with a valid cookie and drops client tenant headers otherwise", async () => {
    const value = await invitePageCookieValue(PAGE, KEY, NOW_S);
    const ok = new Request("https://digithings.ai/chat/api/chat", {
      headers: { referer: "https://digithings.ai/chat/example/", cookie: `example_invite=${value}` },
    });
    await bindInvitePageApiCall(ok, PAGES, ENV, POLICY);
    expect(ok.headers.get(EMBED_TOKEN_HEADER)).toBe(KEY);
    expect(ok.headers.get(EMBED_HOST_HEADER)).toBe("example.test.digithings.ai");

    const spoof = new Request("https://digithings.ai/chat/api/chat", {
      headers: {
        referer: "https://digithings.ai/chat/example/",
        [EMBED_TOKEN_HEADER]: "guess",
        [EMBED_HOST_HEADER]: "example.test.digithings.ai",
      },
    });
    await bindInvitePageApiCall(spoof, PAGES, ENV, POLICY);
    expect(spoof.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
    expect(spoof.headers.get(EMBED_HOST_HEADER)).toBeNull();
  });
  it("leaves calls from other pages and cross-site callers alone", async () => {
    const value = await invitePageCookieValue(PAGE, KEY, NOW_S);
    const house = new Request("https://digithings.ai/chat/api/chat", {
      headers: { referer: "https://digithings.ai/chat/", cookie: `example_invite=${value}`, [EMBED_HOST_HEADER]: "x" },
    });
    await bindInvitePageApiCall(house, PAGES, ENV, POLICY);
    expect(house.headers.get(EMBED_HOST_HEADER)).toBe("x");
    const cross = new Request("https://digithings.ai/chat/api/chat", {
      headers: { referer: "https://evil.test/chat/example/", cookie: `example_invite=${value}` },
    });
    await bindInvitePageApiCall(cross, PAGES, ENV, POLICY);
    expect(cross.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
  });
});

describe("invitePageEmbedGate and cookie stripping", () => {
  it("404s the embed form without the key and passes it with the key", async () => {
    const no = await invitePageEmbedGate(
      new Request("https://digithings.ai/chat/embed?host=example.test.digithings.ai"),
      PAGES,
      ENV,
      notFound,
    );
    expect(no?.status).toBe(404);
    const yes = await invitePageEmbedGate(
      new Request(`https://digithings.ai/embed?host=example.test.digithings.ai&token=${KEY}`),
      PAGES,
      ENV,
      notFound,
    );
    expect(yes).toBeNull();
    const other = await invitePageEmbedGate(new Request("https://digithings.ai/chat/embed?host=digithings.ai"), PAGES, ENV, notFound);
    expect(other).toBeNull();
  });
  it("strips every invite cookie", () => {
    const h = new Headers({ cookie: "occ_invite=a; example_invite=b; example-b_invite=c; keep=d" });
    withoutInvitePageCookies(h, PAGES);
    expect(h.get("cookie")).toBe("keep=d");
  });
});
