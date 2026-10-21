import { describe, expect, it, vi } from "vitest";
import {
  OCC_INVITE_COOKIE,
  SITE_NOT_FOUND_PATH,
} from "../../../../digichat-cloudflare/src/occ-gate";
import { onRequest, type OccPagesContext } from "./[[path]]";

const KEY = "fixture-invite-key";
const SHELL = "<title>OCC help assistant — digichat</title><main class=\"dc-chat-main\">";

/** The site's static 404 page, as the Pages asset server answers any unknown path. */
const SITE_404_BODY =
  '<!DOCTYPE html><html lang="en"><head><title>Page not found — digithings</title></head>' +
  "<body><h1>404</h1></body></html>";
const SITE_404_HEADERS: Record<string, string> = {
  "content-type": "text/html; charset=utf-8",
  "cache-control": "public, max-age=0, must-revalidate",
  "x-content-type-options": "nosniff",
  "referrer-policy": "strict-origin-when-cross-origin",
};
/** Mocked Pages asset server: every path here is one the site does not have. */
const assets = {
  fetch: vi.fn<(req: Request) => Promise<Response>>(async () =>
    new Response(SITE_404_BODY, { status: 404, headers: SITE_404_HEADERS }),
  ),
};

async function snapshot(r: Response) {
  return {
    status: r.status,
    contentType: r.headers.get("content-type"),
    headers: [...r.headers.entries()].sort(),
    body: await r.text(),
  };
}

function ctx(url: string, cookie?: string): OccPagesContext & { next: ReturnType<typeof vi.fn> } {
  const headers = new Headers();
  if (cookie) headers.set("cookie", cookie);
  const next = vi.fn(async () => new Response(SHELL, { status: 200 }));
  return {
    request: new Request(url, { headers }),
    env: {
      OCC_INVITE_KEY: KEY,
      ASSETS: assets,
    },
    next,
  };
}

describe("Pages /chat/occ gate", () => {
  it("404s an uninvited request and does not serve the shell", async () => {
    const c = ctx("https://digithings.ai/chat/occ/");
    const r = await onRequest(c);
    expect(r.status).toBe(404);
    expect(await r.text()).not.toMatch(/dc-chat-main|OCC help assistant/);
    expect(c.next).not.toHaveBeenCalled();
  });

  it("answers a no-key request exactly like a path that does not exist", async () => {
    // The nonexistent-path baseline: what the asset server returns for /xyz
    // and /chat/does-not-exist (no function runs for those paths).
    const baselines = await Promise.all(
      ["https://digithings.ai/xyz", "https://digithings.ai/chat/does-not-exist"].map(async (u) =>
        snapshot(await assets.fetch(new Request(u))),
      ),
    );
    expect(baselines[0]).toEqual(baselines[1]);
    for (const u of [
      "https://digithings.ai/chat/occ",
      "https://digithings.ai/chat/occ/",
      "https://digithings.ai/chat/occ?token=wrong-key",
      "https://digithings.ai/chat/occ/?token=",
    ]) {
      const got = await snapshot(await onRequest(ctx(u)));
      expect(got.status).toBe(404);
      expect(got.contentType).toBe(baselines[0]!.contentType);
      expect(got.body).toBe(baselines[0]!.body);
      expect(got.headers).toEqual(baselines[0]!.headers);
      expect(got.body).not.toMatch(/dc-chat-main|OCC help assistant|<iframe|dboot/);
    }
    // The body really is the site 404 page, not something the gate made up.
    const asked = assets.fetch.mock.calls.map(([req]) => new URL(req.url).pathname);
    expect(asked).toContain(SITE_NOT_FOUND_PATH);
  });

  it("stays a plain 404 when the site 404 cannot be read", async () => {
    for (const asset of [
      async () => new Response("<h1>home</h1>", { status: 200 }),
      async () => {
        throw new Error("assets unavailable");
      },
    ]) {
      const c = ctx("https://digithings.ai/chat/occ");
      c.env.ASSETS = { fetch: asset };
      const r = await onRequest(c);
      expect(r.status).toBe(404);
      expect(r.headers.get("content-type")).toBe("text/html; charset=utf-8");
      expect(await r.text()).not.toContain("home");
      expect(c.next).not.toHaveBeenCalled();
    }
  });

  it("404s when the Pages secret is unset", async () => {
    const c = ctx(`https://digithings.ai/chat/occ/?token=${KEY}`);
    c.env.OCC_INVITE_KEY = undefined;
    const r = await onRequest(c);
    expect(r.status).toBe(404);
    expect(c.next).not.toHaveBeenCalled();
  });

  it("serves the shell for a valid token and sets the invite cookie", async () => {
    const c = ctx(`https://digithings.ai/chat/occ/?token=${KEY}`);
    const r = await onRequest(c);
    expect(r.status).toBe(200);
    expect(c.next).toHaveBeenCalledOnce();
    const cookie = r.headers.get("set-cookie") ?? "";
    expect(cookie).toContain(`${OCC_INVITE_COOKIE}=`);
    expect(cookie).toMatch(/HttpOnly/);
    expect(r.headers.get("cache-control")).toBe("no-store");
  });

  it("serves the shell for the invite cookie on reload", async () => {
    const c = ctx("https://digithings.ai/chat/occ/", `${OCC_INVITE_COOKIE}=${KEY}`);
    const r = await onRequest(c);
    expect(r.status).toBe(200);
    expect(r.headers.get("set-cookie")).toBeNull();
  });
});
