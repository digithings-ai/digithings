import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  EMBED_TOKEN_HEADER,
  inviteTokenValid,
  isInviteOnlyEmbedRequest,
  isOccShellPath,
  OCC_EMBED_HOST,
  OCC_INVITE_COOKIE,
  occContainerRequest,
  occEmbedGate,
  occGate,
} from "./occ-gate";

const KEY = "fixture-invite-key";

/** The site's own 404: what an uninvited request must look like. */
const site = vi.fn(async (_req: Request | string) =>
  new Response("<title>Page not found</title>", {
    status: 404,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "public, max-age=0, must-revalidate",
    },
  }),
);

/** The app's embed route, served by the container. */
const container = vi.fn(
  async (_req: Request) =>
    new Response('<title>OCC help assistant — digichat</title><div class="dc-embed-shell">', {
      status: 200,
      headers: { "content-type": "text/html; charset=utf-8" },
    }),
);

beforeEach(() => {
  site.mockClear();
  container.mockClear();
});

describe("occ gate", () => {
  it("matches only /chat/occ paths", () => {
    expect(isOccShellPath("/chat/occ")).toBe(true);
    expect(isOccShellPath("/chat/occ/")).toBe(true);
    expect(isOccShellPath("/chat")).toBe(false);
    expect(isOccShellPath("/chat/occult")).toBe(false);
  });

  it("validates tokens", () => {
    expect(inviteTokenValid(KEY, KEY)).toBe(true);
    expect(inviteTokenValid("nope", KEY)).toBe(false);
    expect(inviteTokenValid(null, KEY)).toBe(false);
    expect(inviteTokenValid(KEY, undefined)).toBe(false);
  });

  for (const q of ["", "?token=wrong", "?token="]) {
    it(`404s with the site page for '${q}' and never calls the container`, async () => {
      const r = await occGate(new Request(`https://digithings.ai/chat/occ/${q}`), KEY, container, site);
      expect(r.status).toBe(404);
      const body = await r.text();
      expect(body).not.toMatch(/occ|digichat|dc-chat-main/i);
      expect(container).not.toHaveBeenCalled();
      expect(site).toHaveBeenCalled();
    });
  }

  it("serves the app itself for the invite link, not a Pages shell", async () => {
    const r = await occGate(
      new Request(`https://digithings.ai/chat/occ/?token=${KEY}`),
      KEY,
      container,
      site,
    );
    expect(r.status).toBe(200);
    expect(await r.text()).toContain("dc-embed-shell");
    // The 404 upstream is not in the valid path.
    expect(site).not.toHaveBeenCalled();

    const c = r.headers.get("set-cookie") ?? "";
    expect(c).toContain(`${OCC_INVITE_COOKIE}=`);
    expect(c).toMatch(/HttpOnly/);
    expect(c).toMatch(/SameSite=Strict/);
    expect(c).not.toMatch(/Max-Age|Expires/);
    expect(r.headers.get("cache-control")).toBe("no-store");
  });

  it("rewrites the container request and moves the invite out of the URL", async () => {
    await occGate(
      new Request(`https://digithings.ai/chat/occ/?token=${KEY}&utm=x`),
      KEY,
      container,
      site,
    );
    expect(container).toHaveBeenCalledTimes(1);
    const req = container.mock.calls[0]![0];
    const url = new URL(req.url);
    // The app's own embed route, under its base path.
    expect(url.pathname).toBe("/chat/embed");
    // The tenant the container resolves for this shell.
    expect(url.searchParams.get("host")).toBe(OCC_EMBED_HOST);
    // The secret never reaches the container URL.
    expect(url.searchParams.get("token")).toBeNull();
    // Unrelated query parameters are preserved.
    expect(url.searchParams.get("utm")).toBe("x");
    // The app's existing transport, set by the edge.
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBe(KEY);
  });

  it("overwrites a client-supplied embed token rather than trusting it", () => {
    const req = occContainerRequest(
      new Request(`https://digithings.ai/chat/occ/?token=${KEY}`, {
        headers: { [EMBED_TOKEN_HEADER]: "forged" },
      }),
      KEY,
    );
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBe(KEY);
  });

  it("serves the bare path on reload with the cookie, without re-issuing it", async () => {
    const req = new Request("https://digithings.ai/chat/occ/", {
      headers: { cookie: `other=1; ${OCC_INVITE_COOKIE}=${KEY}` },
    });
    const r = await occGate(req, KEY, container, site);
    expect(r.status).toBe(200);
    expect(r.headers.get("set-cookie")).toBeNull();
    expect(container).toHaveBeenCalledTimes(1);
  });

  it("404s a wrong cookie", async () => {
    const req = new Request("https://digithings.ai/chat/occ/", {
      headers: { cookie: `${OCC_INVITE_COOKIE}=wrong` },
    });
    expect((await occGate(req, KEY, container, site)).status).toBe(404);
    expect(container).not.toHaveBeenCalled();
  });

  it("answers no-key /chat/occ and /embed?host=occ like a nonexistent path", async () => {
    const snap = async (r: Response) => ({
      status: r.status,
      contentType: r.headers.get("content-type"),
      headers: [...r.headers.entries()].sort(),
      body: await r.text(),
    });
    const baseline = await snap(await site("https://digithings.ai/xyz"));
    expect(await snap(await site("https://digithings.ai/chat/does-not-exist"))).toEqual(baseline);
    expect(await snap(await occGate(new Request("https://digithings.ai/chat/occ"), KEY, container, site))).toEqual(baseline);
    for (const q of [
      "?host=occ.digithings.ai&layout=page",
      "?host=OCC.digithings.ai.&token=wrong",
      "?host=https://occ.digithings.ai&token=",
    ]) {
      const r = await occEmbedGate(new Request(`https://digithings.ai/embed${q}`), KEY, site);
      expect(r).not.toBeNull();
      expect(await snap(r!)).toEqual(baseline);
    }
  });

  it("gates every spelling of the embed shell (DIG-5121 serves the app under /chat)", () => {
    // The compatibility route.
    expect(
      isInviteOnlyEmbedRequest(new URL("https://digithings.ai/embed?host=occ.digithings.ai")),
    ).toBe(true);
    // The base-path route: the same shell, one path deeper.
    expect(
      isInviteOnlyEmbedRequest(new URL("https://digithings.ai/chat/embed?host=occ.digithings.ai")),
    ).toBe(true);
    expect(
      isInviteOnlyEmbedRequest(
        new URL("https://digithings.ai/chat/embed/x?host=occ.digithings.ai"),
      ),
    ).toBe(true);
    // The app root asked for the embed shell.
    expect(
      isInviteOnlyEmbedRequest(
        new URL("https://digithings.ai/chat/?mode=embed&host=occ.digithings.ai"),
      ),
    ).toBe(true);
    expect(
      isInviteOnlyEmbedRequest(
        new URL("https://digithings.ai/chat?mode=embed&host=occ.digithings.ai"),
      ),
    ).toBe(true);
    // Not the embed surface: the menu and the catalogue.
    expect(
      isInviteOnlyEmbedRequest(new URL("https://digithings.ai/chat?host=occ.digithings.ai")),
    ).toBe(false);
    expect(
      isInviteOnlyEmbedRequest(
        new URL("https://digithings.ai/chat/?mode=catalog&host=occ.digithings.ai"),
      ),
    ).toBe(false);
    // Another tenant on the same paths is not gated.
    expect(
      isInviteOnlyEmbedRequest(new URL("https://digithings.ai/chat/embed?host=digithings.ai")),
    ).toBe(false);
  });

  it("lets an invited or non-gated embed through to the container", async () => {
    expect(await occEmbedGate(new Request(`https://digithings.ai/embed?host=occ.digithings.ai&token=${KEY}`), KEY, site)).toBeNull();
    expect(await occEmbedGate(new Request("https://digithings.ai/embed?host=digithings.ai"), KEY, site)).toBeNull();
    expect(isInviteOnlyEmbedRequest(new URL("https://digithings.ai/api/chat?host=occ.digithings.ai"))).toBe(false);
  });
});
