import { afterEach, describe, expect, it, vi } from "vitest";
import {
  _resetUpstreamAuthCacheForTests,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";

function bffJwt(expSec: number): string {
  const header = Buffer.from(JSON.stringify({ alg: "none" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ exp: expSec })).toString("base64url");
  return `${header}.${payload}.sig`;
}

describe("resolveDigigraphUpstreamAuth cache", () => {
  afterEach(() => {
    _resetUpstreamAuthCacheForTests();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("reuses BFF session JWT within TTL without second exchange", async () => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const token = bffJwt(exp);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: token }),
    });
    vi.stubGlobal("fetch", fetchMock);

    process.env.DIGIKEY_URL = "http://127.0.0.1:8005";
    process.env.DIGIKEY_BFF_TOKEN = "bff-test";
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    const a = await resolveDigigraphUpstreamAuth(req, "acme", "user-1");
    const b = await resolveDigigraphUpstreamAuth(req, "acme", "user-1");

    expect(a.bearer).toBe(token);
    expect(b.bearer).toBe(token);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
