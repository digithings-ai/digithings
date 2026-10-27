import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import {
  bindOccApiCall,
  DIGI_TENANT_HEADER,
  EMBED_HOST_HEADER,
  EMBED_TOKEN_HEADER,
  inviteCookieValid,
  isChatApiPath,
  refererIsOccPage,
  withoutInviteCookie,
  inviteTokenValid,
  isInviteOnlyEmbedRequest,
  isOccShellPath,
  OCC_EMBED_HOST,
  OCC_INVITE_COOKIE,
  occInviteCookieIssuedAt,
  occInviteCookieValue,
  occInviteMaxAgeSeconds,
  OCC_INVITE_DEFAULT_MAX_AGE_DAYS,
  validInviteCookie,
  occContainerRequest,
  occEmbedGate,
  occGate,
} from "./occ-gate";

const KEY = "fixture-invite-key";
/** The cookie value the edge derives from KEY (never KEY itself). */
let COOKIE = "";

/** A fixed clock, so a cookie minted in one test second equals one minted in the next. */
const NOW_MS = Date.UTC(2026, 9, 27, 12, 0, 0);
const NOW_S = NOW_MS / 1000;
const DAY_S = 24 * 60 * 60;

beforeAll(async () => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW_MS });
  COOKIE = await occInviteCookieValue(KEY);
});

afterAll(() => {
  vi.useRealTimers();
});

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

  it("trades the invite link for the cookie, then serves the app itself", async () => {
    const invite = await occGate(
      new Request(`https://digithings.ai/chat/occ/?token=${KEY}`),
      KEY,
      container,
      site,
    );
    // DIG-1437: the key must not stay in the address bar or in history. The
    // edge answers the link with a redirect to the tokenless URL plus the
    // session cookie; the browser re-requests with the cookie.
    expect(invite.status).toBe(302);
    const location = new URL(invite.headers.get("location") ?? "https://x.invalid/");
    expect(location.pathname).toBe("/chat/occ/");
    expect(location.searchParams.get("token")).toBeNull();
    expect(invite.headers.get("cache-control")).toBe("no-store");
    // The redirect is the edge's answer: the container is not woken for it.
    expect(container).not.toHaveBeenCalled();

    const cookies = invite.headers.getSetCookie();
    const c = cookies.find((v) => v.startsWith(`${OCC_INVITE_COOKIE}=${COOKIE}`)) ?? "";
    expect(c).toContain(`${OCC_INVITE_COOKIE}=`);
    expect(c).toMatch(/HttpOnly/);
    expect(c).toMatch(/Secure/);
    expect(c).toMatch(/SameSite=Strict/);
    // Path=/chat, not /chat/occ: the page's own /chat/api/* calls must carry
    // the invite too, or the chat paints and every turn is refused.
    expect(c).toMatch(/Path=\/chat(;|$)/);
    expect(c).not.toMatch(/Max-Age|Expires/);
    // The earlier gate's /chat/occ-scoped cookie is retired in the same answer.
    expect(cookies).toContain(
      `${OCC_INVITE_COOKIE}=; Path=/chat/occ; Max-Age=0; Secure; HttpOnly; SameSite=Strict`,
    );
    expect(invite.headers.get("referrer-policy")).toBe("same-origin");

    // The follow-up request the browser makes, now carrying the cookie.
    const r = await occGate(
      new Request("https://digithings.ai/chat/occ/", {
        headers: { cookie: `${OCC_INVITE_COOKIE}=${COOKIE}` },
      }),
      KEY,
      container,
      site,
    );
    expect(r.status).toBe(200);
    expect(await r.text()).toContain("dc-embed-shell");
    expect(site).not.toHaveBeenCalled();
  });

  it("trims the invite token and the key the way the container does", async () => {
    const r = await occGate(
      new Request(`https://digithings.ai/chat/occ/?token=${encodeURIComponent(` ${KEY}\n`)}`),
      ` ${KEY} `,
      container,
      site,
    );
    expect(r.status).toBe(302);
    expect(r.headers.getSetCookie()).toContain(
      `${OCC_INVITE_COOKIE}=${COOKIE}; Path=/chat; Secure; HttpOnly; SameSite=Strict`,
    );
  });

  it("404s a cookie that holds the raw key (cookies from before the HMAC)", async () => {
    const req = new Request("https://digithings.ai/chat/occ/", {
      headers: { cookie: `${OCC_INVITE_COOKIE}=${KEY}` },
    });
    expect((await occGate(req, KEY, container, site)).status).toBe(404);
    expect(container).not.toHaveBeenCalled();
  });

  it("rewrites the container request and carries the invite as a header", async () => {
    await occGate(
      new Request("https://digithings.ai/chat/occ/?utm=x", {
        headers: { cookie: `${OCC_INVITE_COOKIE}=${COOKIE}` },
      }),
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
    // The app's existing transport, set by the edge — this is what makes the
    // chat turn work on the cookie arm, not just the first paint.
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBe(KEY);
    expect(req.headers.get(EMBED_HOST_HEADER)).toBe(OCC_EMBED_HOST);
    // The cookie stops at the edge.
    expect(req.headers.get("cookie")).toBeNull();
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

  it("serves the bare path on reload with the cookie and moves it to Path=/chat", async () => {
    const req = new Request("https://digithings.ai/chat/occ/", {
      headers: { cookie: `other=1; ${OCC_INVITE_COOKIE}=${COOKIE}` },
    });
    const r = await occGate(req, KEY, container, site);
    expect(r.status).toBe(200);
    // A browser holding a cookie from the earlier /chat/occ-scoped gate gets
    // the same session cookie re-affirmed on /chat (no Max-Age: still a tab
    // session) and the old one expired, so its API calls carry the invite.
    const cookies = r.headers.getSetCookie();
    expect(cookies).toContain(
      `${OCC_INVITE_COOKIE}=${COOKIE}; Path=/chat; Secure; HttpOnly; SameSite=Strict`,
    );
    expect(cookies).toContain(
      `${OCC_INVITE_COOKIE}=; Path=/chat/occ; Max-Age=0; Secure; HttpOnly; SameSite=Strict`,
    );
    expect(r.headers.get("referrer-policy")).toBe("same-origin");
    expect(container).toHaveBeenCalledTimes(1);
    // Other cookies still reach the app; the invite does not.
    expect(container.mock.calls[0]![0].headers.get("cookie")).toBe("other=1");
    // The reload must still authenticate the chat turn, not just paint: the
    // edge puts the key on the container request itself.
    expect(container.mock.calls[0]![0].headers.get(EMBED_TOKEN_HEADER)).toBe(KEY);
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

describe("occ API binding (/chat/api/* from the OCC page)", () => {
  const OCC_PAGE = "https://digithings.ai/chat/occ";
  const HOUSE_PAGE = "https://digithings.ai/chat";

  function apiCall(headers: Record<string, string>, path = "/chat/api/chat"): Request {
    return new Request(`https://digithings.ai${path}`, { method: "POST", headers, body: "{}" });
  }

  it("recognises the app API under its base path only", () => {
    expect(isChatApiPath("/chat/api/chat")).toBe(true);
    expect(isChatApiPath("/chat/api/embed/tenant-config")).toBe(true);
    expect(isChatApiPath("/api/chat")).toBe(false);
    expect(isChatApiPath("/chat/occ")).toBe(false);
    expect(isChatApiPath("/chat/apix")).toBe(false);
  });

  it("knows an OCC page referer only on the same origin", () => {
    expect(refererIsOccPage(apiCall({ referer: OCC_PAGE }))).toBe(true);
    expect(refererIsOccPage(apiCall({ referer: `${OCC_PAGE}/?x=1` }))).toBe(true);
    expect(refererIsOccPage(apiCall({ referer: HOUSE_PAGE }))).toBe(false);
    expect(refererIsOccPage(apiCall({ referer: "https://digithings.ai/chat/occult" }))).toBe(false);
    expect(refererIsOccPage(apiCall({ referer: "https://evil.example/chat/occ" }))).toBe(false);
    expect(refererIsOccPage(apiCall({ referer: "not a url" }))).toBe(false);
    expect(refererIsOccPage(apiCall({}))).toBe(false);
  });

  it("binds a cookie-carrying call from the OCC page to the OCC tenant", async () => {
    const req = apiCall({
      referer: OCC_PAGE,
      cookie: `a=1; ${OCC_INVITE_COOKIE}=${COOKIE}`,
      // What the client sends on its own: the fallback host and no token.
      [EMBED_HOST_HEADER]: "https://digithings.ai",
    });
    await bindOccApiCall(req, KEY);
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBe(KEY);
    expect(req.headers.get(EMBED_HOST_HEADER)).toBe(OCC_EMBED_HOST);
    expect(req.headers.get("cookie")).toBe("a=1");
  });

  it("strips the client's tenant headers from the OCC page without a valid cookie", async () => {
    for (const cookie of [undefined, `${OCC_INVITE_COOKIE}=wrong`, `${OCC_INVITE_COOKIE}=`]) {
      const req = apiCall({
        referer: OCC_PAGE,
        ...(cookie ? { cookie } : {}),
        [EMBED_TOKEN_HEADER]: "forged-or-guessed",
        [EMBED_HOST_HEADER]: OCC_EMBED_HOST,
        [DIGI_TENANT_HEADER]: "occ",
      });
      await bindOccApiCall(req, KEY);
      expect(req.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
      expect(req.headers.get(EMBED_HOST_HEADER)).toBeNull();
      expect(req.headers.get(DIGI_TENANT_HEADER)).toBeNull();
      expect(req.headers.get("cookie")).toBeNull();
    }
  });

  it("fails closed with the Worker secret unset", async () => {
    const req = apiCall({ referer: OCC_PAGE, cookie: `${OCC_INVITE_COOKIE}=${COOKIE}` });
    await bindOccApiCall(req, undefined);
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
    expect(req.headers.get(EMBED_HOST_HEADER)).toBeNull();
  });

  it("never upgrades a house call, even with a valid cookie", async () => {
    const req = apiCall({
      referer: HOUSE_PAGE,
      cookie: `${OCC_INVITE_COOKIE}=${COOKIE}`,
      [EMBED_HOST_HEADER]: "https://digithings.ai",
      [DIGI_TENANT_HEADER]: "occ",
    });
    await bindOccApiCall(req, KEY);
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
    expect(req.headers.get(EMBED_HOST_HEADER)).toBe("https://digithings.ai");
    expect(req.headers.get(DIGI_TENANT_HEADER)).toBeNull();
    expect(req.headers.get("cookie")).toBeNull();
  });

  it("leaves another tenant's own token transport alone", async () => {
    const req = apiCall({
      referer: "https://digithings.ai/embed?host=customer.example",
      [EMBED_TOKEN_HEADER]: "customer-token",
      [EMBED_HOST_HEADER]: "https://customer.example",
    });
    await bindOccApiCall(req, KEY);
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBe("customer-token");
    expect(req.headers.get(EMBED_HOST_HEADER)).toBe("https://customer.example");
  });

  it("accepts any one valid invite cookie among several paths", async () => {
    expect(await inviteCookieValid(`${OCC_INVITE_COOKIE}=old; ${OCC_INVITE_COOKIE}=${COOKIE}`, KEY)).toBe(true);
    expect(await inviteCookieValid(`${OCC_INVITE_COOKIE}=old`, KEY)).toBe(false);
    expect(await inviteCookieValid(null, KEY)).toBe(false);
  });

  it("stores a derived value in the cookie, never the key, and refuses the raw key", async () => {
    expect(COOKIE).not.toBe(KEY);
    expect(COOKIE).not.toContain(KEY);
    expect(COOKIE).toMatch(/^v2\.\d+\.[A-Za-z0-9_-]{43}$/);
    expect(COOKIE.split(".")[1]).toBe(String(NOW_S));
    // Stable for one key and time, different for another key (rotation retires it).
    expect(await occInviteCookieValue(KEY)).toBe(COOKIE);
    expect(await occInviteCookieValue(`${KEY}-rotated`)).not.toBe(COOKIE);
    expect(await inviteCookieValid(`${OCC_INVITE_COOKIE}=${KEY}`, KEY)).toBe(false);
    const raw = apiCall({ referer: OCC_PAGE, cookie: `${OCC_INVITE_COOKIE}=${KEY}` });
    await bindOccApiCall(raw, KEY);
    expect(raw.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
  });

  it("refuses a cross-site or mismatched-origin call even with the OCC Referer", async () => {
    const forms: Array<Record<string, string>> = [
      { "sec-fetch-site": "cross-site" },
      { "sec-fetch-site": "same-site" },
      { "sec-fetch-site": "none" },
      { origin: "https://evil.example" },
      { origin: "https://occ.digithings.ai" },
      { origin: "null" },
    ];
    for (const extra of forms) {
      const req = apiCall({ referer: OCC_PAGE, cookie: `${OCC_INVITE_COOKIE}=${COOKIE}`, ...extra });
      expect(refererIsOccPage(req)).toBe(false);
      await bindOccApiCall(req, KEY);
      expect(req.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
    }
    const ok = apiCall({
      referer: OCC_PAGE,
      cookie: `${OCC_INVITE_COOKIE}=${COOKIE}`,
      "sec-fetch-site": "same-origin",
      origin: "https://digithings.ai",
    });
    expect(refererIsOccPage(ok)).toBe(true);
  });

  it("drops only the invite cookie", () => {
    const h = new Headers({ cookie: `a=1; ${OCC_INVITE_COOKIE}=${COOKIE}; b=2` });
    withoutInviteCookie(h);
    expect(h.get("cookie")).toBe("a=1; b=2");
    const only = new Headers({ cookie: `${OCC_INVITE_COOKIE}=${COOKIE}` });
    withoutInviteCookie(only);
    expect(only.get("cookie")).toBeNull();
  });
});

describe("occ invite cookie lifetime (issued-at inside the MAC)", () => {
  const policy = (days: number, nowMs = NOW_MS) => ({ maxAgeSeconds: days * DAY_S, nowMs });
  const page = (cookie: string) =>
    new Request("https://digithings.ai/chat/occ/", { headers: { cookie } });

  it("reads the max age from the non-secret var, defaulting to 30 days and capped", () => {
    expect(OCC_INVITE_DEFAULT_MAX_AGE_DAYS).toBe(30);
    expect(occInviteMaxAgeSeconds(undefined)).toBe(30 * DAY_S);
    expect(occInviteMaxAgeSeconds("")).toBe(30 * DAY_S);
    expect(occInviteMaxAgeSeconds("7")).toBe(7 * DAY_S);
    expect(occInviteMaxAgeSeconds(" 14 ")).toBe(14 * DAY_S);
    // Zero, negative, fractional or junk never means "no expiry".
    for (const bad of ["0", "-1", "1.5", "abc", "30d", "1e3"]) {
      expect(occInviteMaxAgeSeconds(bad)).toBe(30 * DAY_S);
    }
    expect(occInviteMaxAgeSeconds("9999")).toBe(365 * DAY_S);
  });

  it("accepts a cookie up to the max age and refuses it one second later", async () => {
    const issued = await occInviteCookieValue(KEY, NOW_S - 30 * DAY_S);
    expect(await occInviteCookieIssuedAt(issued, KEY, policy(30))).toBe(NOW_S - 30 * DAY_S);
    expect(await occInviteCookieIssuedAt(issued, KEY, policy(30, NOW_MS + 1000))).toBeNull();
    expect(await occInviteCookieIssuedAt(issued, KEY, policy(7))).toBeNull();
  });

  it("404s an expired cookie on /chat/occ and never wakes the container", async () => {
    const old = await occInviteCookieValue(KEY, NOW_S - 31 * DAY_S);
    const r = await occGate(page(`${OCC_INVITE_COOKIE}=${old}`), KEY, container, site, policy(30));
    expect(r.status).toBe(404);
    expect(container).not.toHaveBeenCalled();
    expect(r.headers.getSetCookie()).toEqual([]);
  });

  it("does not bind an expired cookie on the chat API", async () => {
    const old = await occInviteCookieValue(KEY, NOW_S - 31 * DAY_S);
    const req = new Request("https://digithings.ai/chat/api/chat", {
      method: "POST",
      headers: {
        referer: "https://digithings.ai/chat/occ/",
        "sec-fetch-site": "same-origin",
        cookie: `${OCC_INVITE_COOKIE}=${old}`,
      },
    });
    await bindOccApiCall(req, KEY, policy(30));
    expect(req.headers.get(EMBED_TOKEN_HEADER)).toBeNull();
    expect(req.headers.get(EMBED_HOST_HEADER)).toBeNull();
    expect(req.headers.get("cookie")).toBeNull();
  });

  it("refuses a tampered issued-at, a tampered MAC, a future issued-at and old formats", async () => {
    const good = await occInviteCookieValue(KEY, NOW_S - DAY_S);
    const [, iat, mac] = good.split(".") as [string, string, string];
    const flipped = `${mac.slice(0, -1)}${mac.endsWith("A") ? "B" : "A"}`;
    const forms = [
      `v2.${Number(iat) + DAY_S}.${mac}`, // a renewed issued-at under the old MAC
      `v2.${iat}.${flipped}`,
      `v1.${iat}.${mac}`,
      `v2.${iat}`,
      `v2.${iat}.${mac}.x`,
      `v2.-5.${mac}`,
      `v2.${iat}x.${mac}`,
      mac, // the v1 shape: a MAC alone
      KEY, // the raw key
    ];
    for (const value of forms) {
      expect(await occInviteCookieIssuedAt(value, KEY, policy(30))).toBeNull();
      const r = await occGate(page(`${OCC_INVITE_COOKIE}=${value}`), KEY, container, site, policy(30));
      expect(r.status).toBe(404);
    }
    // Minted for the future (beyond clock skew) with a VALID MAC: still refused.
    const future = await occInviteCookieValue(KEY, NOW_S + DAY_S);
    expect(await occInviteCookieIssuedAt(future, KEY, policy(30))).toBeNull();
    // A few seconds of skew is tolerated.
    const skew = await occInviteCookieValue(KEY, NOW_S + 60);
    expect(await occInviteCookieIssuedAt(skew, KEY, policy(30))).toBe(NOW_S + 60);
    expect(container).not.toHaveBeenCalled();
  });

  it("retires every cookie when the key is rotated", async () => {
    const before = await occInviteCookieValue(KEY, NOW_S);
    expect(await occInviteCookieIssuedAt(before, `${KEY}-rotated`, policy(30))).toBeNull();
    const r = await occGate(
      page(`${OCC_INVITE_COOKIE}=${before}`),
      `${KEY}-rotated`,
      container,
      site,
      policy(30),
    );
    expect(r.status).toBe(404);
  });

  it("re-issues a fresh cookie on a valid ?token= hit, even over an expired one", async () => {
    const old = await occInviteCookieValue(KEY, NOW_S - 40 * DAY_S);
    const r = await occGate(
      new Request(`https://digithings.ai/chat/occ/?token=${KEY}`, {
        headers: { cookie: `${OCC_INVITE_COOKIE}=${old}` },
      }),
      KEY,
      container,
      site,
      policy(30),
    );
    expect(r.status).toBe(302);
    const set = r.headers
      .getSetCookie()
      .find((v) => v.startsWith(`${OCC_INVITE_COOKIE}=v2.`)) ?? "";
    const value = decodeURIComponent(set.slice(`${OCC_INVITE_COOKIE}=`.length).split(";")[0]!);
    expect(await occInviteCookieIssuedAt(value, KEY, policy(30))).toBe(NOW_S);
    expect(value).not.toBe(old);
  });

  it("never extends a session on a cookie hit: it re-sets the same issued-at", async () => {
    const issued = await occInviteCookieValue(KEY, NOW_S - 10 * DAY_S);
    const r = await occGate(page(`${OCC_INVITE_COOKIE}=${issued}`), KEY, container, site, policy(30));
    expect(r.status).toBe(200);
    expect(r.headers.getSetCookie()).toContain(
      `${OCC_INVITE_COOKIE}=${issued}; Path=/chat; Secure; HttpOnly; SameSite=Strict`,
    );
  });

  it("picks the newest valid cookie when a browser sends several", async () => {
    const older = await occInviteCookieValue(KEY, NOW_S - 20 * DAY_S);
    const newer = await occInviteCookieValue(KEY, NOW_S - 2 * DAY_S);
    const expired = await occInviteCookieValue(KEY, NOW_S - 90 * DAY_S);
    const header = `${OCC_INVITE_COOKIE}=${expired}; ${OCC_INVITE_COOKIE}=${older}; ${OCC_INVITE_COOKIE}=${newer}`;
    expect(await validInviteCookie(header, KEY, policy(30))).toBe(newer);
    expect(await validInviteCookie(`${OCC_INVITE_COOKIE}=${expired}`, KEY, policy(30))).toBeNull();
  });
});
