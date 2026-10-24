import { afterEach, describe, expect, it, vi } from "vitest";
import {
  _resetUpstreamAuthCacheForTests,
  DigigraphUpstreamAuthError,
  DigigraphUpstreamUnavailableError,
  resolveDigigraphUpstreamAuth,
} from "@/lib/digigraph-upstream";

function bffJwt(expSec: number): string {
  const header = Buffer.from(JSON.stringify({ alg: "none" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ exp: expSec })).toString("base64url");
  return `${header}.${payload}.sig`;
}

const PREV_ENV = {
  DIGIKEY_URL: process.env.DIGIKEY_URL,
  DIGIKEY_BFF_TOKEN: process.env.DIGIKEY_BFF_TOKEN,
  DIGIGRAPH_UPSTREAM_API_KEY: process.env.DIGIGRAPH_UPSTREAM_API_KEY,
};

function restoreEnv(): void {
  for (const [key, value] of Object.entries(PREV_ENV)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

afterEach(() => {
  _resetUpstreamAuthCacheForTests();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
  restoreEnv();
});

describe("resolveDigigraphUpstreamAuth cache", () => {
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
    delete process.env.DIGIGRAPH_UPSTREAM_API_KEY;
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    const a = await resolveDigigraphUpstreamAuth(req, "acme", "user-1");
    const b = await resolveDigigraphUpstreamAuth(req, "acme", "user-1");

    expect(a.bearer).toBe(token);
    expect(b.bearer).toBe(token);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("exchanges and caches Authorization Bearer dgk_live_ material", async () => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const token = bffJwt(exp);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: token,
        litellm_proxy_api_key: "llmk",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    process.env.DIGIKEY_URL = "http://127.0.0.1:8005";
    delete process.env.DIGIKEY_BFF_TOKEN;
    delete process.env.DIGIGRAPH_UPSTREAM_API_KEY;

    const req = new Request("http://localhost/api/chat", {
      method: "POST",
      headers: { authorization: "Bearer dgk_live_abcdefghijklmnop" },
    });

    const a = await resolveDigigraphUpstreamAuth(req, "acme", "user-1");
    const b = await resolveDigigraphUpstreamAuth(req, "acme", "user-1");

    expect(a).toEqual({ bearer: token, litellmProxyApiKey: "llmk" });
    expect(b.bearer).toBe(token);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].body).toContain("api_key");
  });
});

describe("resolveDigigraphUpstreamAuth failures and fallbacks", () => {
  it("throws when api_key exchange fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) })
    );
    process.env.DIGIKEY_URL = "http://127.0.0.1:8005";
    delete process.env.DIGIKEY_BFF_TOKEN;
    delete process.env.DIGIGRAPH_UPSTREAM_API_KEY;

    const req = new Request("http://localhost/api/chat", {
      headers: { authorization: "Bearer dgk_live_deadbeefdeadbeef" },
    });

    await expect(resolveDigigraphUpstreamAuth(req, "acme", "user-1")).rejects.toThrow(
      DigigraphUpstreamAuthError
    );
    await expect(resolveDigigraphUpstreamAuth(req, "acme", "user-1")).rejects.toThrow(
      /api_key exchange failed/
    );
  });

  it("throws when DIGIKEY_URL is set without DIGIKEY_BFF_TOKEN or key material", async () => {
    process.env.DIGIKEY_URL = "http://127.0.0.1:8005";
    delete process.env.DIGIKEY_BFF_TOKEN;
    delete process.env.DIGIGRAPH_UPSTREAM_API_KEY;
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    await expect(resolveDigigraphUpstreamAuth(req, "acme", "user-1")).rejects.toThrow(
      /DIGIKEY_BFF_TOKEN is missing/
    );
  });

  it("falls back to DIGIGRAPH_UPSTREAM_API_KEY when digikey exchange is unavailable", async () => {
    delete process.env.DIGIKEY_URL;
    delete process.env.DIGIKEY_BFF_TOKEN;
    process.env.DIGIGRAPH_UPSTREAM_API_KEY = "static-upstream-key";
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    await expect(resolveDigigraphUpstreamAuth(req, "acme", "user-1")).resolves.toEqual({
      bearer: "static-upstream-key",
      litellmProxyApiKey: null,
    });
  });

  it("throws a configuration error when no upstream auth path is configured", async () => {
    delete process.env.DIGIKEY_URL;
    delete process.env.DIGIKEY_BFF_TOKEN;
    delete process.env.DIGIGRAPH_UPSTREAM_API_KEY;
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    await expect(resolveDigigraphUpstreamAuth(req, "acme", "user-1")).rejects.toThrow(
      /Set DIGIKEY_URL \+ DIGIKEY_BFF_TOKEN/
    );
  });
});

describe("resolveDigigraphUpstreamAuth bff_session failure reasons", () => {
  function bffEnv(): void {
    process.env.DIGIKEY_URL = "http://127.0.0.1:8005";
    process.env.DIGIKEY_BFF_TOKEN = "bff-test";
    delete process.env.DIGRAPH_UPSTREAM_API_KEY;
  }

  it("raises an unavailable error, not an auth error, when digikey is cold", async () => {
    // digikey answers with a transient status on every attempt: the container
    // is asleep. That is a cold dependency, so the error must not blame the
    // token and must not be an auth error (DIG-4424).
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) })
    );
    bffEnv();
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    const settled = resolveDigigraphUpstreamAuth(req, "acme", "user-1").then(
      () => null,
      (e: unknown) => e
    );
    await vi.advanceTimersByTimeAsync(60_000);
    const err = await settled;

    expect(err).toBeInstanceOf(DigigraphUpstreamUnavailableError);
    expect(err).not.toBeInstanceOf(DigigraphUpstreamAuthError);
    expect(String((err as Error).message)).toContain("not a DIGIKEY_BFF_TOKEN problem");
  });

  it("raises an auth error, not an unavailable error, when digikey has no bff_session grant", async () => {
    // digikey answers 503 when its own env has no DIGIKEY_BFF_TOKEN, so its
    // bff_session grant does not exist. Waiting cannot install the missing
    // secret, and the copy on the digichat side is not the one that is wrong
    // (DIG-4424).
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({}),
        text: async () =>
          JSON.stringify({
            detail: "bff_session grant not configured (DIGIKEY_BFF_TOKEN)",
          }),
      })
    );
    bffEnv();
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    const err = await resolveDigigraphUpstreamAuth(req, "acme", "user-1").then(
      () => null,
      (e: unknown) => e
    );

    expect(err).toBeInstanceOf(DigigraphUpstreamAuthError);
    expect(err).not.toBeInstanceOf(DigigraphUpstreamUnavailableError);
    expect(String((err as Error).message)).toContain("digikey side");
  });

  it("raises an auth error when digikey refuses the token", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) })
    );
    bffEnv();
    const req = new Request("http://localhost/api/chat", { method: "POST" });

    const err = await resolveDigigraphUpstreamAuth(req, "acme", "user-1").then(
      () => null,
      (e: unknown) => e
    );

    expect(err).toBeInstanceOf(DigigraphUpstreamAuthError);
    expect(err).not.toBeInstanceOf(DigigraphUpstreamUnavailableError);
    expect(String((err as Error).message)).toContain("DIGIKEY_BFF_TOKEN");
    expect(String((err as Error).message)).toContain("rejected");
  });
});
