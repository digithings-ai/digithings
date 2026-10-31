import { afterEach, describe, expect, it, vi } from "vitest";
import {
  _resetUpstreamAuthCacheForTests,
  apiKeyCacheKey,
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

describe("resolveDigigraphUpstreamAuth api_key cache is keyed on the full key", () => {
  // Obviously fake fixtures. The first 16 characters are the public key
  // prefix digikey shows and logs; the two keys share it and differ after.
  const FIXTURE_PREFIX = "dgk_live_fixtur_";
  const OWNER_KEY = `${FIXTURE_PREFIX}owner-suffix-not-a-real-key`;
  const OTHER_KEY = `${FIXTURE_PREFIX}attacker-guess-not-a-real-key`;

  function apiKeyEnv(): void {
    process.env.DIGIKEY_URL = "http://127.0.0.1:8005";
    delete process.env.DIGIKEY_BFF_TOKEN;
    delete process.env.DIGIGRAPH_UPSTREAM_API_KEY;
  }

  function reqWith(key: string): Request {
    return new Request("http://localhost/api/chat", {
      method: "POST",
      headers: { authorization: `Bearer ${key}` },
    });
  }

  function exchangedKey(call: unknown[]): string | null {
    const body = String((call[1] as { body?: unknown } | undefined)?.body ?? "");
    try {
      const parsed = JSON.parse(body) as { api_key?: unknown };
      return typeof parsed.api_key === "string" ? parsed.api_key : null;
    } catch {
      return null;
    }
  }

  it("fixtures share the 16-char public prefix", () => {
    expect(OWNER_KEY.slice(0, 16)).toBe(FIXTURE_PREFIX);
    expect(OTHER_KEY.slice(0, 16)).toBe(FIXTURE_PREFIX);
    expect(OWNER_KEY).not.toBe(OTHER_KEY);
  });

  it("the owner's full key exchanges once, then hits the cache", async () => {
    const ownerJwt = bffJwt(Math.floor(Date.now() / 1000) + 3600);
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: ownerJwt }),
    });
    vi.stubGlobal("fetch", fetchMock);
    apiKeyEnv();

    const a = await resolveDigigraphUpstreamAuth(reqWith(OWNER_KEY), "acme", "user-1");
    const b = await resolveDigigraphUpstreamAuth(reqWith(OWNER_KEY), "acme", "user-1");

    expect(a.bearer).toBe(ownerJwt);
    expect(b.bearer).toBe(ownerJwt);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("a key with the owner's prefix but another suffix misses and is refused", async () => {
    const ownerJwt = bffJwt(Math.floor(Date.now() / 1000) + 3600);
    // The mock digikey knows only the owner's key; anything else is rejected.
    const fetchMock = vi.fn().mockImplementation(async (_url: unknown, init: unknown) => {
      if (exchangedKey([_url, init]) === OWNER_KEY) {
        return { ok: true, json: async () => ({ access_token: ownerJwt }) };
      }
      return { ok: false, status: 401, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);
    apiKeyEnv();

    const owner = await resolveDigigraphUpstreamAuth(reqWith(OWNER_KEY), "acme", "user-1");
    expect(owner.bearer).toBe(ownerJwt);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const err = await resolveDigigraphUpstreamAuth(reqWith(OTHER_KEY), "acme", "user-1").then(
      (auth) => auth,
      (e: unknown) => e
    );

    expect(err).toBeInstanceOf(DigigraphUpstreamAuthError);
    expect(JSON.stringify(err)).not.toContain(ownerJwt);
    // It went to digikey with its own key instead of being served from cache.
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(exchangedKey(fetchMock.mock.calls[1])).toBe(OTHER_KEY);
  });

  it("a key with the owner's prefix gets its own JWT, never the owner's", async () => {
    const exp = Math.floor(Date.now() / 1000) + 3600;
    const ownerJwt = `${bffJwt(exp)}owner`;
    const otherJwt = `${bffJwt(exp)}other`;
    const fetchMock = vi.fn().mockImplementation(async (_url: unknown, init: unknown) => ({
      ok: true,
      json: async () => ({
        access_token: exchangedKey([_url, init]) === OWNER_KEY ? ownerJwt : otherJwt,
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    apiKeyEnv();

    await resolveDigigraphUpstreamAuth(reqWith(OWNER_KEY), "acme", "user-1");
    const other = await resolveDigigraphUpstreamAuth(reqWith(OTHER_KEY), "acme", "user-1");
    const ownerAgain = await resolveDigigraphUpstreamAuth(reqWith(OWNER_KEY), "acme", "user-1");

    expect(other.bearer).toBe(otherJwt);
    expect(other.bearer).not.toBe(ownerJwt);
    expect(ownerAgain.bearer).toBe(ownerJwt);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("the cache key holds neither the raw key nor its prefix", () => {
    const ownerKey = apiKeyCacheKey(OWNER_KEY);
    const otherKey = apiKeyCacheKey(OTHER_KEY);

    expect(ownerKey).toMatch(/^api_key:sha256:[0-9a-f]{64}$/);
    expect(ownerKey).not.toContain(OWNER_KEY);
    expect(ownerKey).not.toContain(FIXTURE_PREFIX);
    expect(ownerKey).not.toContain(FIXTURE_PREFIX.replace(/_$/, ""));
    expect(ownerKey).not.toBe(otherKey);
    expect(apiKeyCacheKey(OWNER_KEY)).toBe(ownerKey);
  });
});
