import { describe, expect, it, vi } from "vitest";
import { inviteTokenValid, isOccShellPath, OCC_INVITE_COOKIE, occGate } from "./occ-gate";

const KEY = "fixture-invite-key";
const pages = vi.fn(async (req: Request | string) => {
  const u = typeof req === "string" ? req : req.url;
  return new URL(u).pathname.startsWith("/chat/occ")
    ? new Response("<title>OCC help assistant — digichat</title><main class=\"dc-chat-main\">", {
        status: 200,
      })
    : new Response("<title>Page not found</title>", { status: 404 });
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
    it(`404s with the site page for '${q}'`, async () => {
      const r = await occGate(new Request(`https://digithings.ai/chat/occ/${q}`), KEY, pages);
      expect(r.status).toBe(404);
      expect(r.headers.get("cache-control")).toBe("no-store");
      const body = await r.text();
      expect(body).not.toMatch(/occ|digichat|dc-chat-main/i);
    });
  }
  it("serves the shell for the invite link and sets the tab-session cookie", async () => {
    const r = await occGate(new Request(`https://digithings.ai/chat/occ/?token=${KEY}`), KEY, pages);
    expect(r.status).toBe(200);
    const c = r.headers.get("set-cookie") ?? "";
    expect(c).toContain(`${OCC_INVITE_COOKIE}=`);
    expect(c).toMatch(/HttpOnly/);
    expect(c).toMatch(/SameSite=Strict/);
    expect(c).not.toMatch(/Max-Age|Expires/);
    expect(r.headers.get("cache-control")).toBe("no-store");
  });
  it("serves the bare path on reload with the cookie", async () => {
    const req = new Request("https://digithings.ai/chat/occ/", {
      headers: { cookie: `other=1; ${OCC_INVITE_COOKIE}=${KEY}` },
    });
    const r = await occGate(req, KEY, pages);
    expect(r.status).toBe(200);
    expect(r.headers.get("set-cookie")).toBeNull();
  });
  it("404s a wrong cookie", async () => {
    const req = new Request("https://digithings.ai/chat/occ/", {
      headers: { cookie: `${OCC_INVITE_COOKIE}=wrong` },
    });
    expect((await occGate(req, KEY, pages)).status).toBe(404);
  });
});
