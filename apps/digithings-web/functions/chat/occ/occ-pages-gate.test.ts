import { describe, expect, it, vi } from "vitest";
import { OCC_INVITE_COOKIE } from "../../../../digichat-cloudflare/src/occ-gate";
import { onRequest, type OccPagesContext } from "./[[path]]";

const KEY = "fixture-invite-key";
const SHELL = "<title>OCC help assistant — digichat</title><main class=\"dc-chat-main\">";

function ctx(url: string, cookie?: string): OccPagesContext & { next: ReturnType<typeof vi.fn> } {
  const headers = new Headers();
  if (cookie) headers.set("cookie", cookie);
  const next = vi.fn(async () => new Response(SHELL, { status: 200 }));
  return {
    request: new Request(url, { headers }),
    env: {
      OCC_INVITE_KEY: KEY,
      ASSETS: {
        fetch: async () => new Response("<title>Page not found</title>", { status: 404 }),
      },
    },
    next,
  };
}

describe("Pages /chat/occ gate", () => {
  it("404s an uninvited request and does not serve the shell", async () => {
    const c = ctx("https://digithings.ai/chat/occ/");
    const r = await onRequest(c);
    expect(r.status).toBe(404);
    expect(r.headers.get("cache-control")).toBe("no-store");
    expect(await r.text()).not.toMatch(/dc-chat-main|OCC help assistant/);
    expect(c.next).not.toHaveBeenCalled();
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
