import { describe, expect, it, vi } from "vitest";
import { inviteTokenValid, isOccShellPath, occGate } from "./occ-gate";

const KEY = "fixture-invite-key";
const pages = vi.fn(async (req: Request | string) => {
  const u = typeof req === "string" ? req : req.url;
  return new URL(u).pathname.startsWith("/chat/occ")
    ? new Response("<title>OCC help assistant — digichat</title>", { status: 200 })
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
      const body = await r.text();
      expect(body).not.toMatch(/occ|digichat/i);
    });
  }
  it("serves the shell for the invite link", async () => {
    const r = await occGate(new Request(`https://digithings.ai/chat/occ/?token=${KEY}`), KEY, pages);
    expect(r.status).toBe(200);
  });
});
