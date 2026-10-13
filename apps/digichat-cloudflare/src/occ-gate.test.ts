import { describe, expect, it } from "vitest";
import { isOccPagePath, occInviteValid, siteNotFound } from "./occ-gate";

describe("occ gate", () => {
  it("matches only the OCC page paths", () => {
    expect(isOccPagePath("/chat/occ")).toBe(true);
    expect(isOccPagePath("/chat/occ/")).toBe(true);
    expect(isOccPagePath("/chat")).toBe(false);
    expect(isOccPagePath("/chat/occult")).toBe(false);
  });
  it("needs the exact invite key", () => {
    const u = (q: string) => new URL(`https://digithings.ai/chat/occ/${q}`);
    expect(occInviteValid(u("?token=abc"), "abc")).toBe(true);
    expect(occInviteValid(u("?token=abd"), "abc")).toBe(false);
    expect(occInviteValid(u(""), "abc")).toBe(false);
    expect(occInviteValid(u("?token=abc"), undefined)).toBe(false);
    expect(occInviteValid(u("?token="), "")).toBe(false);
  });
  it("serves the site's not-found page with status 404", async () => {
    const fake = (async () => new Response("<h1>404</h1>", { status: 404, headers: { "content-type": "text/html" } })) as typeof fetch;
    const r = await siteNotFound(new URL("https://digithings.ai/chat/occ/"), fake);
    expect(r.status).toBe(404);
    expect(await r.text()).toBe("<h1>404</h1>");
  });
});
